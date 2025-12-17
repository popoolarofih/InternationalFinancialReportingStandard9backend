import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm

from ..functions import (
    clean_date_column,
    clean_input_sheet,
    clean_numeric_columns,
    strip_n_upper,
)
from .forecast_parser import parse_fli_forecast_sheet
from .scenario_weights import get_scenario_weights

def get_fli_model(fli_file_path = r"worktemplates\Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx", historical_sheet = "FLI Historical Data", forecast_sheet = "FLI Forecast Data", scenario_weight_sheet = "Scenario Weight Historical Data", scenario_output_dict={}):
    """
    fli_file_path: Input File for FLI
    """
    # Check input data

    # Read the Historical input data and forecast scenarios
    try:
        historical_input_df = pd.read_excel(fli_file_path, sheet_name=historical_sheet)
    except Exception as e:
        print(f"Error reading 'FLI Historical Data' sheet: {e}")
        return None

    if historical_input_df.empty:
        print("Error: historical_input_df is empty")
        return None

    # --- Load forecast sheet ---
    forecast_df = pd.read_excel(fli_file_path, sheet_name=forecast_sheet)
    forecast_df = parse_fli_forecast_sheet(forecast_df)

    # --- Get scenario weights ---
    scenario_output_dict = get_scenario_weights(fli_file_path, scenario_weight_sheet)
    if scenario_output_dict is None:
        print("Error: get_scenario_weights returned None")
        return None

    scenario_weights_base_stats_df = scenario_output_dict["scenario_weights_base_stats_df"]
    historical_scenario_weights_combo = scenario_output_dict["historical_scenario_weights_combo"]
    scenario_weights_summary_stats = scenario_output_dict["scenario_weights_summary_stats"]

    # --- Validate ---
    if "MEV" not in forecast_df.columns or forecast_df["MEV"].nunique() == 0:
        raise ValueError(
            f"Forecast sheet malformed: missing or empty MEV column.\n"
            f"Columns found: {list(forecast_df.columns)}"
        )

    # --- Safe division ---
    num_mevs = forecast_df["MEV"].nunique()
    num_records = len(forecast_df)
    fli_forecast_input_record_count = num_records / num_mevs if num_mevs > 0 else 0

    print(
        f"Debug: Forecast contains {num_mevs} MEVs across {num_records} records "
        f"({fli_forecast_input_record_count:.1f} periods)."
    )

    fli_forecast_input_count_check = fli_forecast_input_record_count

    # Convert data types appropriately
    for cols in historical_input_df.columns:
        if cols != "Period":
            historical_input_df[cols] = pd.to_numeric(historical_input_df[cols], errors="coerce") # Convert to floats
        else:
            historical_input_df[cols] = pd.to_datetime(historical_input_df[cols], format="mixed", errors="coerce") # Convert to Date
    
    # Check for NaT in Period
    if historical_input_df["Period"].isna().all():
        print("Error: All 'Period' values are NaT after conversion")
        return None

    # Get and introduce mean and Standard Deviation
    _mean = historical_input_df.select_dtypes(include="number").mean()
    _std = historical_input_df.select_dtypes(include="number").std(ddof=0)

    # Add identifiers and convert to Dataframes
    _mean["Period"] = "Mean" # identifier
    _mean = pd.DataFrame([_mean]) # to dataframe

    _std["Period"] = "Standard Deviation" # identifier
    _std = pd.DataFrame([_std]) # to dataframe

    # Convert the historical date column to str
    historical_input_df["Period"] = historical_input_df["Period"].dt.strftime("%Y-%m-%d")

    # Append the Mean and Standard Deviations to the original DataFrame
    historical_input_df = pd.concat(
        [historical_input_df.iloc[:0,:], _mean, _std, historical_input_df], ignore_index=True
    ) # uses an empty dataframe as the start to use its existing column structure

    # Strip and upper case column names for consistency
    historical_input_df = strip_n_upper(historical_input_df, [col for col in historical_input_df.columns if col != 'Period'])

    # Determine and store the direction of each MEV
    mev_name = [cols for cols in historical_input_df.columns if cols not in {"Period", "Identifier"}]
    mev_direction = [
        "Positive" if "prime" in str(cols).lower() else 
        "Negative" if "gdp" in str(cols).lower() else 
        "Negative" if "oil" in str(cols).lower() else
        "Positive" if "infla" in str(cols).lower() else
        "Positive" if "unemployment" in str(cols).lower() else
        "Positive" for cols in mev_name
    ]

    # Get Z Scores
    historical_z_score = historical_input_df.copy()
    
    for cols in historical_z_score.columns:
        if "npl" in cols.lower():
            npl_col_name = cols
            historical_z_score = historical_z_score.drop(columns=[cols])
        elif cols == "Period":
            historical_z_score[cols] = pd.to_datetime(historical_z_score[cols], format="mixed", errors="coerce")

    # Check if historical_z_score has enough rows
    if len(historical_z_score) < 3:
        print(f"Error: historical_z_score has only {len(historical_z_score)} rows, need at least 3")
        return None

    _mean = historical_z_score.iloc[0, 1:].astype(float)
    _std = historical_z_score.iloc[1, 1:].astype(float)
    historical_z_score = historical_z_score.iloc[2:]
    
    # Drop rows with NaN in Period
    historical_z_score = historical_z_score[historical_z_score["Period"].notna()].reset_index(drop=True)
    print("Debug: historical_z_score shape after dropping NaN:", historical_z_score.shape)
    print("Debug: historical_z_score Period values:", historical_z_score["Period"].dt.strftime("%b %Y").tolist())

    # Check if enough data remains
    if len(historical_z_score) < 5:
        print(f"Error: historical_z_score has only {len(historical_z_score)} rows after dropping NaN, need at least 5")
        return None

    n_qrts_for_corr_data = min(20, len(historical_z_score))  # Adjust to available data
    print("Debug: n_qrts_for_corr_data:", n_qrts_for_corr_data)
    recent_n_qrts_from_historical = historical_z_score.iloc[-n_qrts_for_corr_data:].copy()
    print("Debug: recent_n_qrts_from_historical shape:", recent_n_qrts_from_historical.shape)
    print("Debug: recent_n_qrts_from_historical Period values:", recent_n_qrts_from_historical["Period"].dt.strftime("%b %Y").tolist())

    for cols in recent_n_qrts_from_historical.columns:
        if cols.lower() not in {"period", "npl"}:
            recent_n_qrts_from_historical[cols] = historical_input_df.iloc[2:][historical_input_df["Period"].notna()][npl_col_name].values[-n_qrts_for_corr_data:]

    historical_z_score.iloc[:, 1:] = (historical_z_score.iloc[:, 1:] - _mean) / _std

    # Lag Calculations
    # Define helper function to find closest date
    def find_closest_date(df, target_date, date_type, lag):
        if pd.isna(target_date):
            print(f"Error: {date_type}_date_lag_{lag} is NaT")
            return None
        target_str = target_date.strftime("%b %Y")
        filtered = df[df["Period"].dt.strftime("%b %Y") == target_str]
        if not filtered.empty:
            return filtered.index[0]
        # Find closest date
        df["date_diff"] = abs(df["Period"] - target_date)
        closest_date = df.loc[df["date_diff"].idxmin()]
        print(f"Warning: No exact match for {date_type}_date_lag_{lag} ({target_str}), using closest date: {closest_date['Period'].strftime('%b %Y')}")
        return closest_date.name

    # Calculate lag dates
    max_date_lag_12 = historical_z_score["Period"].iloc[:-(n_qrts_for_corr_data-16)].max() if len(historical_z_score) > (n_qrts_for_corr_data-16) else pd.NaT
    min_date_lag_12 = max_date_lag_12 + pd.offsets.MonthEnd(-(n_qrts_for_corr_data-1)*3) if pd.notna(max_date_lag_12) else pd.NaT

    max_date_lag_9 = historical_z_score["Period"].iloc[:-(n_qrts_for_corr_data-17)].max() if len(historical_z_score) > (n_qrts_for_corr_data-17) else pd.NaT
    min_date_lag_9 = max_date_lag_9 + pd.offsets.MonthEnd(-(n_qrts_for_corr_data-1)*3) if pd.notna(max_date_lag_9) else pd.NaT

    max_date_lag_6 = historical_z_score["Period"].iloc[:-(n_qrts_for_corr_data-18)].max() if len(historical_z_score) > (n_qrts_for_corr_data-18) else pd.NaT
    min_date_lag_6 = max_date_lag_6 + pd.offsets.MonthEnd(-(n_qrts_for_corr_data-1)*3) if pd.notna(max_date_lag_6) else pd.NaT

    max_date_lag_3 = historical_z_score["Period"].iloc[:-(n_qrts_for_corr_data-19)].max() if len(historical_z_score) > (n_qrts_for_corr_data-19) else pd.NaT
    min_date_lag_3 = max_date_lag_3 + pd.offsets.MonthEnd(-(n_qrts_for_corr_data-1)*3) if pd.notna(max_date_lag_3) else pd.NaT

    max_date_lag_0 = historical_z_score["Period"].max()
    min_date_lag_0 = max_date_lag_0 + pd.offsets.MonthEnd(-(n_qrts_for_corr_data-1)*3) if pd.notna(max_date_lag_0) else pd.NaT

    # Debug: Print dates
    print("Debug: max_date_lag_12:", max_date_lag_12)
    print("Debug: min_date_lag_12:", min_date_lag_12)
    print("Debug: max_date_lag_0:", max_date_lag_0)
    print("Debug: min_date_lag_0:", min_date_lag_0)

    # Get indices with checks
    lag_12_max_ind = find_closest_date(historical_z_score, max_date_lag_12, "max", 12)
    lag_12_min_ind = find_closest_date(historical_z_score, min_date_lag_12, "min", 12)
    lag_9_max_ind = find_closest_date(historical_z_score, max_date_lag_9, "max", 9)
    lag_9_min_ind = find_closest_date(historical_z_score, min_date_lag_9, "min", 9)
    lag_6_max_ind = find_closest_date(historical_z_score, max_date_lag_6, "max", 6)
    lag_6_min_ind = find_closest_date(historical_z_score, min_date_lag_6, "min", 6)
    lag_3_max_ind = find_closest_date(historical_z_score, max_date_lag_3, "max", 3)
    lag_3_min_ind = find_closest_date(historical_z_score, min_date_lag_3, "min", 3)
    lag_0_max_ind = find_closest_date(historical_z_score, max_date_lag_0, "max", 0)
    lag_0_min_ind = find_closest_date(historical_z_score, min_date_lag_0, "min", 0)

    if None in [lag_12_max_ind, lag_12_min_ind, lag_9_max_ind, lag_9_min_ind, lag_6_max_ind, lag_6_min_ind, lag_3_max_ind, lag_3_min_ind, lag_0_max_ind, lag_0_min_ind]:
        print("Error: One or more lag indices could not be determined, skipping lag calculations")
        return None

    # Drop the temporary date_diff column added during closest date finding
    historical_z_score.drop(columns=['date_diff'], inplace=True, errors='ignore')

    # Getting Correlation Scores
    lag_months = [0, 3, 6, 9, 12]
    min_ind_list = [lag_0_min_ind, lag_3_min_ind, lag_6_min_ind, lag_9_min_ind, lag_12_min_ind]
    max_ind_list = [lag_0_max_ind, lag_3_max_ind, lag_6_max_ind, lag_9_max_ind, lag_12_max_ind]

    corr_df = pd.DataFrame({})
    for lag_month, min_ind, max_ind in zip(lag_months, min_ind_list, max_ind_list):
        z_score_data = historical_z_score.loc[min_ind:max_ind].reset_index(drop=True)
        z_score_data = z_score_data.iloc[:n_qrts_for_corr_data].dropna()  # Ensure same number of rows
        if z_score_data.empty:
            print(f"Error: z_score_data for lag {lag_month} is empty")
            continue
        print(f"Debug: z_score_data for lag {lag_month} shape:", z_score_data.shape)
        print(f"Debug: z_score_data for lag {lag_month} Period values:", z_score_data["Period"].dt.strftime("%b %Y").tolist())
        for cols in z_score_data.columns:
            if cols not in {"Period"}:
                # Ensure both arrays have the same length
                min_length = min(len(z_score_data[cols]), len(recent_n_qrts_from_historical[cols]))
                z_score_data_subset = z_score_data[cols].iloc[:min_length].dropna()
                recent_subset = recent_n_qrts_from_historical[cols].iloc[:min_length].dropna()
                if len(z_score_data_subset) < 2 or len(recent_subset) < 2:
                    print(f"Warning: Insufficient data for correlation of {cols} at lag {lag_month}, skipping")
                    continue
                if len(z_score_data_subset) != len(recent_subset):
                    print(f"Warning: Mismatch in data lengths for {cols} at lag {lag_month}: z_score_data ({len(z_score_data_subset)}), recent_n_qrts ({len(recent_subset)})")
                    continue
                corr_result = np.corrcoef(z_score_data_subset, recent_subset)[0, 1]
                df = pd.DataFrame(
                    {
                        "Lag Month": [lag_month],
                        "MEV": [cols],
                        "Corr Value": [corr_result]
                    }
                )
                corr_df = pd.concat([corr_df, df], ignore_index=True)

    print("Debug: corr_df:\n", corr_df.to_string())

    # Validate the correlation scores and select best signed lags; fallback to top-abs-corr if too few
    # First pass: for each MEV, keep only lags that match the a-priori sign, then pick the lag with max abs correlation.
    corr_df_validation = pd.DataFrame([], columns=["Lag Month", "MEV", "Corr Value", "best_lag_state", "best_corr_value"])
    mev_direction_map = dict(zip(mev_name, mev_direction))
    for each_mev in corr_df["MEV"].unique():
        direction = mev_direction_map.get(each_mev, "Positive")
        df_mev = corr_df[corr_df["MEV"] == each_mev].copy()
        if df_mev.empty:
            corr_df_validation = pd.concat([corr_df_validation, pd.DataFrame([{
                "Lag Month": 0,
                "MEV": each_mev,
                "Corr Value": np.nan,
                "best_lag_state": "Wrong Sign",
                "best_corr_value": np.nan
            }])], ignore_index=True)
            continue

        # Filter by expected sign
        if direction == "Positive":
            valid_lags = df_mev[df_mev["Corr Value"] > 0].copy()
        else:
            valid_lags = df_mev[df_mev["Corr Value"] < 0].copy()

        if valid_lags.empty:
            corr_df_validation = pd.concat([corr_df_validation, pd.DataFrame([{
                "Lag Month": 0,
                "MEV": each_mev,
                "Corr Value": np.nan,
                "best_lag_state": "Wrong Sign",
                "best_corr_value": np.nan
            }])], ignore_index=True)
        else:
            idx_best = valid_lags["Corr Value"].abs().idxmax()
            best_row = valid_lags.loc[idx_best]
            corr_df_validation = pd.concat([corr_df_validation, pd.DataFrame([{
                "Lag Month": int(best_row["Lag Month"]),
                "MEV": each_mev,
                "Corr Value": best_row["Corr Value"],
                "best_lag_state": int(best_row["Lag Month"]),
                "best_corr_value": best_row["Corr Value"]
            }])], ignore_index=True)

    correlation_analysis = corr_df_validation.pivot_table(
        index="Lag Month",
        columns=["MEV", "best_lag_state"],
        values="Corr Value"
    )

    # Make an Excel-writable (single-level) copy of the pivot for output:
    try:
        corr_df_validation_flat = correlation_analysis.copy()
        if isinstance(corr_df_validation_flat.columns, pd.MultiIndex):
            # flatten MultiIndex columns into single strings
            corr_df_validation_flat.columns = [
                "_".join([str(c).strip() for c in col if c is not None and str(c) != ""])
                for col in corr_df_validation_flat.columns.values
            ]
        corr_df_validation_flat = corr_df_validation_flat.reset_index()
    except Exception as _e:
        # Fallback: convert to simple DataFrame with string representation
        corr_df_validation_flat = pd.DataFrame({
            "pivot": correlation_analysis.astype(str).stack().reset_index().apply(lambda r: f"{r[0]}_{r[1]}_{r[2]}", axis=1)
        })

    # Build the base selection from correctly-signed MEVs only
    corr_df_base = corr_df_validation[corr_df_validation["best_lag_state"] != "Wrong Sign"].copy()

    # If not enough MEVs or lack sign diversity, fallback to best-by-abs-correlation (up to 4 MEVs),
    # while trying to enforce at least one positive and one negative correlated MEV.
    def fallback_select_top_mevs(all_corr_df, target_n=4):
        # pick the row per MEV with max abs corr
        best_per_mev = all_corr_df.loc[all_corr_df.groupby("MEV")["Corr Value"].apply(lambda s: s.abs().idxmax())].copy()
        best_per_mev["abs_corr"] = best_per_mev["Corr Value"].abs()
        candidates = best_per_mev.sort_values("abs_corr", ascending=False).copy()
        selected = []
        # pick up to target_n ensuring sign diversity if possible
        for _, row in candidates.iterrows():
            if len(selected) >= target_n:
                break
            selected.append(row)
        if not selected:
            return pd.DataFrame()
        sel_df = pd.DataFrame(selected)
        # ensure at least one positive and one negative corr if possible
        if (sel_df["Corr Value"] > 0).any() and (sel_df["Corr Value"] < 0).any():
            return sel_df
        # try to swap in opposite sign from remaining candidates
        if not ((sel_df["Corr Value"] > 0).any()):
            # need a positive candidate
            pos_candidate = candidates[candidates["Corr Value"] > 0]
            if not pos_candidate.empty:
                # replace last element
                sel_df.iloc[-1] = pos_candidate.iloc[0]
        if not ((sel_df["Corr Value"] < 0).any()):
            neg_candidate = candidates[candidates["Corr Value"] < 0]
            if not neg_candidate.empty:
                sel_df.iloc[-1] = neg_candidate.iloc[0]
        return sel_df

    # Decide whether fallback is required
    use_fallback = False
    if corr_df_base.empty or len(corr_df_base) < 2:
        use_fallback = True
    else:
        # check sign diversity in corr_df_base using actual correlation signs
        signs = np.sign(corr_df_base["Corr Value"].dropna())
        if not ((signs > 0).any() and (signs < 0).any()):
            use_fallback = True

    if use_fallback:
        # build candidate using full corr_df (not sign-filtered)
        fallback_df = fallback_select_top_mevs(corr_df, target_n=4)
        if not fallback_df.empty:
            corr_df_base = fallback_df[["MEV", "Lag Month", "Corr Value"]].rename(columns={"Lag Month":"best_lag_state", "Corr Value":"best_corr_value"})
            corr_df_base = corr_df_base[["MEV", "best_lag_state", "best_corr_value"]].copy()
        else:
            # nothing to use; keep corr_df_base empty (downstream code handles)
            corr_df_base = corr_df_base

    # Normalize corr_df_base columns types
    if not corr_df_base.empty:
        corr_df_base["best_lag_state"] = corr_df_base["best_lag_state"].astype(float)
        corr_df_base["best_corr_value"] = corr_df_base["best_corr_value"].astype(float)
    wrong_signed_mevs = [col for col in corr_df_validation["MEV"].unique() if col not in corr_df_base["MEV"].unique()]

    # Prepare historical input slices and determine reference index for lag calculations
    historical_input_copy = historical_input_df.iloc[2:].copy()
    historical_input_copy["Period"] = pd.to_datetime(historical_input_copy["Period"], format="mixed", errors="coerce")
    # keep only rows with valid Period and within the recent window used for lagging
    historical_input_copy = historical_input_copy[historical_input_copy["Period"].notna()]
    if pd.notna(min_date_lag_0):
        historical_input_copy = historical_input_copy[pd.to_datetime(historical_input_copy["Period"]) > (min_date_lag_0 + relativedelta(months=-1))]

    hist_input_copy = historical_input_df.copy()
    hist_input_copy["Period"] = pd.to_datetime(hist_input_copy["Period"], errors="coerce", format="mixed")
    hist_input_copy = hist_input_copy[hist_input_copy["Period"].notna()].reset_index(drop=True).reset_index()

    # determine reference date and its index in hist_input_copy (used as starting point for lag slices)
    ref_date = pd.to_datetime(historical_input_copy["Period"], format="mixed", errors="coerce").min() if not historical_input_copy.empty else None
    if ref_date is None:
        print("Error: Could not determine reference date from historical_input_copy")
        return None
    ref_date_index = hist_input_copy[hist_input_copy["Period"] == ref_date].index[0] if not hist_input_copy[hist_input_copy["Period"] == ref_date].empty else None
    if ref_date_index is None:
        print("Error: Could not find reference date in hist_input_copy")
        return None

    # Initialize historical_lagged_df with Period and NPL column for alignment
    historical_lagged_df = (
        hist_input_copy[
            (hist_input_copy["index"] >= ref_date_index) &
            (hist_input_copy["index"] < ref_date_index + n_qrts_for_corr_data)
        ]
        [["Period", npl_col_name]].reset_index(drop=True)
    )

    # Append MEV columns (selected by corr_df_base) to historical_lagged_df
    for mev, lag in zip(corr_df_base["MEV"].values, corr_df_base["best_lag_state"].values):
        start_ind = int(ref_date_index - (lag / 3))
        df = hist_input_copy[
            (hist_input_copy["index"] >= start_ind) &
            (hist_input_copy["index"] < start_ind + n_qrts_for_corr_data)
        ][mev].reset_index(drop=True)
        historical_lagged_df = pd.concat([historical_lagged_df, df], axis=1)

    # If after everything we still have very few MEVs, warn but continue; downstream regression will validate
    if historical_lagged_df.select_dtypes(include="number").shape[1] <= 1:
        print("Warning: Few or no MEVs selected after lag selection and fallback. Regression likely to be weak.")

    # Ensure numeric and drop rows with NaN before regression
    historical_lagged_df = historical_lagged_df.apply(pd.to_numeric, errors="ignore")
    historical_lagged_df = historical_lagged_df.dropna(axis=0, how="any")

    avg_historic_npl = (
        historical_lagged_df.select_dtypes(include="number").mean()
    )
    avg_historic_npl["Period"] = "Average Historic NPL"
    avg_historic_npl = pd.DataFrame([avg_historic_npl])

    for cols in avg_historic_npl.columns:
        if cols not in {"Period", npl_col_name}:
            avg_historic_npl[cols] = np.nan
    
    historical_lagged_df["Period"] = historical_lagged_df["Period"].astype(str)
    historical_lagged_df = pd.concat(
        [historical_lagged_df, pd.DataFrame([np.nan], columns=["Period"]), avg_historic_npl], ignore_index=True
    )

    # REGRESSION MODEL ANALYSIS on lagged Data
    # drop final summary rows and rows with NaNs so OLS has matching row counts
    regression_model_data = historical_lagged_df.iloc[:-2].copy().reset_index(drop=True)
    regression_model_data = regression_model_data.dropna(axis=0, how="any").reset_index(drop=True)
    cols_to_exclude = ["Period", npl_col_name]
    all_regression_run_dict = {}
    regression_result_to_excel_sheet = {}
    flag = 0
    counter = 1
    fli_run_validation_df = pd.DataFrame({})
    
    while flag == 0:
        each_regression_run = {}
        independent_vars = [cols for cols in regression_model_data.columns if cols not in cols_to_exclude]
        if len(independent_vars) == 0:
            print("No independent variables left for regression.")
            model_run_status = "Not Good"
            flag += 1
            continue
        X = regression_model_data[independent_vars]
        X = sm.add_constant(X)
        y = regression_model_data[npl_col_name]
        regression_model_result = sm.OLS(y, X).fit()

        y_pred = regression_model_result.fittedvalues
        y_actual = y
        correlation_matrix = np.corrcoef(y_actual, y_pred)
        multiple_r = abs(correlation_matrix[0, 1])
        standard_error = np.sqrt(regression_model_result.mse_resid)
        r_squared = regression_model_result.rsquared
        adjusted_r_squared = regression_model_result.rsquared_adj
        num_observations = regression_model_result.nobs
        fvalue = regression_model_result.fvalue
        f_pvalue = regression_model_result.f_pvalue
        llf = regression_model_result.llf
        aic = regression_model_result.aic
        bic = regression_model_result.bic
        ssr = regression_model_result.ess
        sse = regression_model_result.ssr
        sst = ssr + sse
        df_regression = len(independent_vars)
        df_residual = regression_model_result.df_resid
        df_total = df_regression + df_residual
        ms_regression = ssr / df_regression if df_regression > 0 else np.nan
        ms_residual = sse / df_residual if df_residual > 0 else np.nan
        f_stat = ms_regression / ms_residual if ms_residual != 0 else np.nan

        coefficients = regression_model_result.params
        coefficients = coefficients.map("{:.9g}".format)
        coefficients = pd.DataFrame(coefficients).reset_index()
        coefficients.columns = ["Variables", "Coefficients"]

        p_value = regression_model_result.pvalues
        p_values = pd.DataFrame(p_value).reset_index()
        p_values.columns = ["Variables", "P-values"]

        coefficient_variables = (
            coefficients.merge(
                p_values,
                how="left",
                on="Variables"
            )
        )

        coefficient_variables["Variables"] = ["Intercept" if var == "const" else var for var in coefficient_variables["Variables"].values]

        anova_table = pd.DataFrame({
            " ": ["Regression", "Residual", "Total"],
            "df": ["{:,.0f}".format(df_regression), "{:,.0f}".format(df_residual), "{:,.0f}".format(df_total)],
            "SS": ["{:.9g}".format(ssr), "{:.9g}".format(sse), "{:.9g}".format(sst)],
            "MS": ["{:.9g}".format(ms_regression), "{:.9g}".format(ms_residual), np.nan],
            "F": ["{:.9g}".format(f_stat), np.nan, np.nan],
            "Significance F": ["{:.9g}".format(f_pvalue), np.nan, np.nan],
        })

        coefficients_to_excel = regression_model_result.params
        standard_errors_to_excel = regression_model_result.bse
        t_values_to_excel = regression_model_result.tvalues
        p_values_to_excel = regression_model_result.pvalues
        conf_int_to_excel = regression_model_result.conf_int()

        results_df_to_excel = pd.DataFrame({
            "Coefficients": coefficients_to_excel,
            "Standard Error": standard_errors_to_excel,
            "t Stat": t_values_to_excel,
            "P-value": p_values_to_excel,
            "Lower 95%": conf_int_to_excel[0],
            "Upper 95%": conf_int_to_excel[1]
        }).map("{:.9g}".format).reset_index()

        results_df_to_excel["index"] = ["Intercept" if var == "const" else var for var in results_df_to_excel["index"].values]
        results_df_to_excel = results_df_to_excel.rename(columns={"index":" "})

        summary_stats_to_excel = {
            "Multiple R": "{:.9g}".format(multiple_r),
            "R Square": "{:.9g}".format(r_squared),
            "Adjusted R Square": "{:.9g}".format(adjusted_r_squared),
            "Standard Errors": "{:.9g}".format(standard_error),
            "Observations": "{:,.0f}".format(num_observations),
        }

        summary_df_to_excel = pd.DataFrame(list(summary_stats_to_excel.items()), columns=["Metric", "Value"])

        write_regression_result_to_excel_sheet = {
            "summary_df_to_excel": summary_df_to_excel,
            "anova_table": anova_table,
            "results_df_to_excel": results_df_to_excel
        }

        regression_result_to_excel_sheet[f"Regression Result{counter}"] = write_regression_result_to_excel_sheet

        regression_stat_dict = {
            "Multiple R": multiple_r,
            "R Square": r_squared,
            "Adjusted R Square": adjusted_r_squared,
            "Standard Errors": standard_error,
            "Observations": num_observations,
        }
        regression_stat_df = pd.DataFrame([regression_stat_dict]).T.reset_index()
        regression_stat_df.columns = ["Statistics", "Value"]
        regression_stat_df["Check"] = (
            np.where(
                regression_stat_df["Statistics"].isin(["Standard Errors", "Observations"]),
                "",
                np.where(
                    regression_stat_df["Value"] >= 0.75, "Perfect",
                    np.where(
                        regression_stat_df["Value"] >= 0.45, "Good",
                        "Not Good"
                    )
                )
            )
        )

        regression_stat_df["Value"] = (
            np.where(
                regression_stat_df["Statistics"].isin(["Observations"]),
                regression_stat_df["Value"],
                (regression_stat_df["Value"]*100).round(2).astype(str) + "%"
            )
        )

        regression_result = regression_model_result.summary()

        p_above_threshold = p_values[(p_values["Variables"] != "const") & (p_values["P-values"] > 0.05)]
        p_above_threshold_var = p_above_threshold["Variables"].unique()
        mev_name_n_direction = pd.DataFrame(zip(mev_name, mev_direction), columns=["Variables", "Direction"])
        p_values_w_direction = p_values.merge(
            mev_name_n_direction, how="left", on="Variables"
        )
        # Check if at least one positive and one negative MEV remain after dropping
        remaining_vars = [var for var in p_values["Variables"] if var != "const" and var not in p_above_threshold_var]
        remaining_directions = mev_name_n_direction[mev_name_n_direction["Variables"].isin(remaining_vars)]["Direction"].unique()
        direction_validity = ("Positive" in remaining_directions) and ("Negative" in remaining_directions)
        
        if len(p_above_threshold) > 0 or not direction_validity:
            cols_to_exclude = cols_to_exclude + (p_above_threshold_var.tolist())
            model_run_status = "Not Good"
            flag += 0
        elif (
            (len(p_above_threshold) == 0) and 
            (len(p_values[(p_values["Variables"] != "const") & (p_values["P-values"] <= 0.05)]) >= 2) and 
            (adjusted_r_squared >= 0.45) and
            direction_validity
        ):
            model_run_status = "Good"
            flag += 1
        else:
            model_run_status = "Not Good"
            flag += 1

        MEV_p_Values = p_values[p_values["Variables"] != "const"].copy()
        MEV_p_Values["mev_p_value"] = MEV_p_Values["Variables"] + " - " + MEV_p_Values["P-values"].round(6).astype("str")
        MEV_p_Values_concat = "; ".join(MEV_p_Values["mev_p_value"])

        run_validation_summary = (
            pd.DataFrame(
                {
                    "Run": [counter],
                    "Adjusted R-Squared": [adjusted_r_squared],
                    "MEV P-Values": [MEV_p_Values_concat],
                    "Status": model_run_status
                }
            )
        )

        fli_run_validation_df = pd.concat([fli_run_validation_df, run_validation_summary], ignore_index=True)
        
        each_regression_run["MEV Dropped"] = p_above_threshold_var.tolist()
        each_regression_run["coefficient_variables"] = coefficient_variables
        each_regression_run["regression_model_result"] = regression_model_result
        each_regression_run["regression_stat_df"] = regression_stat_df
        each_regression_run["regression_result"] = regression_result
        all_regression_run_dict[f"Correlation_Run_{counter}"] = each_regression_run

        counter += 1

    mevs_dropped = [mev for mev in cols_to_exclude if mev not in ["Period", npl_col_name]]
    count_of_mev_dropped = len(mevs_dropped)
    
    p_values_copy = p_values[p_values["Variables"] != "const"]
    if model_run_status == "Good":
        if count_of_mev_dropped >= 2:
            custom_text_join = "; ".join(mevs_dropped)
            model_message = f"After {counter-1} Regression runs and dropping {count_of_mev_dropped} MEVs ({custom_text_join}), \n See Regression Summary Output below:"
        else:
            custom_text_join = "; ".join(mevs_dropped)
            model_message = f"After {counter-1} Regression runs and dropping {count_of_mev_dropped} MEV ({custom_text_join}), \n See Regression Summary Output below:"
    else:
        model_message = "Model Failed"

    fli_run_validation = {
        "Overall Verdict": model_run_status,
        "Message": model_message,
        "Table": fli_run_validation_df
    }

    # Get Coefficient of value on lagged Data
    coef_of_intercept = float(coefficient_variables[coefficient_variables["Variables"]=="Intercept"]["Coefficients"].iloc[0])
    qualifying_mev = coefficient_variables[~coefficient_variables["Variables"].isin(["Intercept"])]["Variables"].values

    scalar_output = forecast_df[forecast_df["MEV"].isin(qualifying_mev)].copy()
    scalar_output_all_mev = scalar_output.copy()

    scalar_output = (
        scalar_output.merge(
            coefficient_variables.rename(columns={"Variables": "MEV"}),
            on="MEV",
            how="left"
        )
    )

    scalar_output["Base Scenario"] = scalar_output["Base Scenario"] * scalar_output["Coefficients"].astype(float)
    scalar_output["Best Scenario"] = scalar_output["Best Scenario"] * scalar_output["Coefficients"].astype(float)
    scalar_output["Worst Scenario"] = scalar_output["Worst Scenario"] * scalar_output["Coefficients"].astype(float)

    scalar_output = (
        scalar_output.pivot_table(
            index="Period",
            values=["Base Scenario", "Worst Scenario", "Best Scenario"],
            aggfunc="sum"
        ).reset_index()
    )
    print("Debug: scalar_output after pivot shape:", scalar_output.shape)
    print("Debug: scalar_output after pivot columns:", scalar_output.columns.tolist())
    print("Debug: scalar_output after pivot head:\n", scalar_output.head())

    if 'Base Scenario' not in scalar_output.columns:
        scalar_output['Base Scenario'] = 0
        scalar_output['Best Scenario'] = 0
        scalar_output['Worst Scenario'] = 0

    for col in ["Base Scenario", "Best Scenario", "Worst Scenario"]:
        scalar_output[col] = (
            scalar_output[col] + coef_of_intercept
        )
        scalar_output[f"scalar{col}"] = (
            scalar_output[col] / avg_historic_npl[npl_col_name].values[0]
        )

    scalar_output = scalar_output.iloc[-8:]

    # FLI SCALARS
    forecast_industry_npl = scalar_output[["Period", "Base Scenario", "Worst Scenario", "Best Scenario"]]
    forecast_scalars = scalar_output[["Period", "scalarBase Scenario", "scalarWorst Scenario", "scalarBest Scenario"]]
    forecast_scalars.columns = [col.replace("scalar","") for col in forecast_scalars.columns]


    if scenario_weights_summary_stats.empty:
        fli_scalar_weight = pd.DataFrame({'Scenarios': ['Base', 'Upturn', 'Downturn'], 'Weights': [1.0, 0.0, 0.0]})
        scenario_weights_summary_stats_T = pd.DataFrame()
        summary_scenario_weights = pd.DataFrame()
        base_weight = 1.0
        upturn_weight = 0.0
        downturn_weight = 0.0
    else:
        scenario_weights_summary_stats_T = scenario_weights_summary_stats.T.copy()
        scenario_weights_summary_stats_T.columns = scenario_weights_summary_stats_T.iloc[0]
        scenario_weights_summary_stats_T = scenario_weights_summary_stats_T.iloc[1:].reset_index().rename(columns={"index":"Statistics"})

        summary_scenario_weights = scenario_weights_summary_stats[["MEV", "Base", "Upturn", "Downturn"]]
        summary_scenario_weights = (
            pd.melt(
                summary_scenario_weights,
                id_vars=["MEV"],
                var_name="Scenarios",
            ).pivot_table(
                index="Scenarios",
                columns="MEV",
                values="value",
                aggfunc="mean"
            ).reset_index()
        )

        df_total = summary_scenario_weights.select_dtypes(include="number").sum().sum()
        if df_total == 0:
            summary_scenario_weights["Weights"] = [1.0/3, 1.0/3, 1.0/3]  # equal if zero
        else:
            summary_scenario_weights["Weights"] = summary_scenario_weights.select_dtypes(include="number").sum(axis=1) / df_total

        fli_scalar_weight = summary_scenario_weights[["Scenarios", "Weights"]]
        
        base_weight = fli_scalar_weight[fli_scalar_weight["Scenarios"] == "Base"]["Weights"].iloc[0] if not fli_scalar_weight[fli_scalar_weight["Scenarios"] == "Base"].empty else 1.0
        upturn_weight = fli_scalar_weight[fli_scalar_weight["Scenarios"] == "Upturn"]["Weights"].iloc[0] if not fli_scalar_weight[fli_scalar_weight["Scenarios"] == "Upturn"].empty else 0.0
        downturn_weight = fli_scalar_weight[fli_scalar_weight["Scenarios"] == "Downturn"]["Weights"].iloc[0] if not fli_scalar_weight[fli_scalar_weight["Scenarios"] == "Downturn"].empty else 0.0

    fli_scalar_weights_per_qrt = forecast_scalars.copy()
    fli_scalar_weights_per_qrt["WEIGHTED SCALARS"] = (
        (fli_scalar_weights_per_qrt["Base Scenario"] * base_weight) + 
        (fli_scalar_weights_per_qrt["Best Scenario"] * upturn_weight) + 
        (fli_scalar_weights_per_qrt["Worst Scenario"] * downturn_weight)
    )

    Quarter_no_list = list(range(1, 41))
    desired_rows = 40
    fli_scalar_weights_per_qrt = fli_scalar_weights_per_qrt.reindex(range(desired_rows))
    fli_scalar_weights_per_qrt["Quarters"] = Quarter_no_list
    fli_scalar_weights_per_qrt = fli_scalar_weights_per_qrt[["Quarters", "Base Scenario", "Best Scenario", "Worst Scenario", "WEIGHTED SCALARS"]]
    fli_scalar_weights_per_qrt = fli_scalar_weights_per_qrt.T
    fli_scalar_weights_per_qrt.columns = fli_scalar_weights_per_qrt.iloc[0].astype(int)
    fli_scalar_weights_per_qrt = fli_scalar_weights_per_qrt.iloc[1:]
    fli_scalar_weights_per_qrt.iloc[:, 8:] = 1

    fli_scalar_weights_per_qrt = fli_scalar_weights_per_qrt.to_dict(orient="list")
    fli_scalar_weight = fli_scalar_weight.to_dict(orient="list")

    # RELEVANT OUTPUTS TO DICTIONARY
    fli_output_dict = {
        "mev_forecast_quarterly": forecast_df,
        "historical_input_df": historical_input_df,
        "historical_z_score": historical_z_score,
        "correlation_analysis": correlation_analysis,
        "historical_lagged_df": historical_lagged_df,
        "fli_forecast_input_count_check": fli_forecast_input_count_check,
        # corr_df_validation is a flattened, Excel-writable copy of the pivot
        "corr_df_validation": corr_df_validation_flat,
         "all_regression_run_dict": all_regression_run_dict,
         "regression_result_to_excel_sheet": regression_result_to_excel_sheet,
         "regression_model_result": regression_model_result.summary2().tables[1],
         "regression_result": regression_result,
         "regression_stat_df": regression_stat_df,
         "coefficient_variables": coefficient_variables,
         "scalar_output_all_mev": scalar_output_all_mev,
         "forecast_industry_npl": forecast_industry_npl,
         "forecast_scalars": forecast_scalars,
         "fli_scalar_weight": fli_scalar_weight,
         "fli_scalar_weights_per_qrt": fli_scalar_weights_per_qrt,
         "fli_run_validation": fli_run_validation,
         "scenario_weights_base_stats_df": scenario_weights_base_stats_df,
         "historical_scenario_weights_combo": historical_scenario_weights_combo,
         "scenario_weights_summary_stats": scenario_weights_summary_stats,
         "scenario_weights_summary_stats_T": scenario_weights_summary_stats_T,
         "summary_scenario_weights": summary_scenario_weights,
         "qualifying_mev": qualifying_mev,
     }

    # Before return, add debug for qualifying_mev and scalar_output_all_mev
    print("Debug: qualifying_mev:", qualifying_mev)
    print("Debug: scalar_output_all_mev shape:", scalar_output_all_mev.shape)
    print("Debug: scalar_output_all_mev columns:", scalar_output_all_mev.columns.tolist())
    print("Debug: scalar_output_all_mev head:\n", scalar_output_all_mev.head())

    return fli_output_dict


