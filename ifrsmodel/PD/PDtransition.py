# PDtransitionWorkbook.py
import pandas as pd
import numpy as np
import logging
import os
import sys

# Add the parent directory to sys.path to import from ifrsmodel.PD
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ifrsmodel.PD.pdinput import load_pd_input, preprocess_pd_data
from ifrsmodel.PD.PDmodel import calculate_pd_migration
from ifrsmodel.PD.PDmigration import calculate_total_year_sum

logging.basicConfig(level=logging.WARNING)


# -----------------------------
# 1) Cumulative PDs (Workbook style)
# -----------------------------
def calculate_cumulative_pds(df, sectors, quarters):
    """
    Workbook-style cumulative PDs for each sector:
    - Compute hazard q = P->D / (P->P + P->D) from PD INPUT data.
    - Apply constant hazard q across quarters.
    - Cumulative PD(t) = 1 - (1-q)^(t+1).
    """
    results = []
    col_names = [q.strftime('%b %Y') for q in quarters]

    for sector in sectors:
        df_sector = df[df['Business sector'] == sector].copy()

        is_perf = df_sector['Performance classification 2'] == 'Performing'
        not_na_next = df_sector['PD Performance after qtr 1'].astype(str).str.upper() != 'NA'

        ob = df_sector.loc[is_perf & not_na_next, 'Outstanding Balance (₦)']
        to_state = df_sector.loc[is_perf & not_na_next, 'PD Performance after qtr 1']

        p_to_p = float(ob[to_state == 'Performing'].sum())
        p_to_d = float(ob[to_state == 'Default'].sum())
        p_total = p_to_p + p_to_d
        q = (p_to_d / p_total) if p_total > 0 else 0.0

        survival = 1.0
        cumulative_pds = []
        for _ in range(len(quarters)):
            survival *= (1.0 - q)
            cumulative_pds.append(1.0 - survival)

        results.append(cumulative_pds)

    return pd.DataFrame(results, index=sectors, columns=col_names)


# -----------------------------
# 2) Conditional PDs (Quarterly)
# -----------------------------
def calculate_conditional_pds(cumulative_pd_df):
    # Assuming constant hazard rate h_q, conditional PD is h_q for all quarters
    h_q = cumulative_pd_df.iloc[:, 0]  # h_q is the cumulative PD for the first quarter
    cond = pd.DataFrame(
        np.tile(h_q.values, (cumulative_pd_df.shape[1], 1)).T,
        index=cumulative_pd_df.index,
        columns=cumulative_pd_df.columns
    )
    return cond


# -----------------------------
# 3) Conditional PDs (Monthly)
# -----------------------------
def calculate_conditional_pds_monthly(conditional_pd_df, calibration_factors=None):
    """
    Convert quarterly conditional PDs to monthly conditional PDs by solving
    1 - (1 - h_m)^3 = h_q  =>  h_m = 1 - (1 - h_q)^(1/3).

    Accepts optional calibration_factors to multiply each sector's monthly
    rate (either a list aligned to index order or a dict keyed by sector).
    Results are clipped to [0, 1].
    """
    months_per_quarter = 3
    total_months = conditional_pd_df.shape[1] * months_per_quarter
    monthly_cols = [f"Month {i}" for i in range(1, total_months + 1)]
    monthly_df = pd.DataFrame(index=conditional_pd_df.index, columns=monthly_cols, dtype=float)

    # Prepare calibration factors per sector (default = 1.0)
    if calibration_factors is None:
        calibration_map = {sector: 1.0 for sector in conditional_pd_df.index}
    elif isinstance(calibration_factors, dict):
        calibration_map = {sector: float(calibration_factors.get(sector, 1.0)) for sector in conditional_pd_df.index}
    else:
        # assume iterable/list aligned with index
        try:
            calibration_map = {sector: float(calibration_factors[i]) if i < len(calibration_factors) else 1.0
                               for i, sector in enumerate(conditional_pd_df.index)}
        except Exception:
            calibration_map = {sector: 1.0 for sector in conditional_pd_df.index}

    for sector in conditional_pd_df.index:
        monthly_values = []
        # For each quarterly conditional PD, compute equivalent monthly hazard
        for qtr_pd in conditional_pd_df.loc[sector].values.astype(float):
            # Ensure qtr_pd is within [0,1]
            q = max(0.0, min(1.0, qtr_pd))
            # Solve for monthly hazard: h_m = 1 - (1 - h_q)^(1/3)
            monthly_pd = 1.0 - (1.0 - q) ** (1.0 / months_per_quarter)
            # Apply calibration factor for this sector
            monthly_pd *= calibration_map.get(sector, 1.0)
            # Clip to valid probability range
            monthly_pd = max(0.0, min(1.0, monthly_pd))
            # Repeat the monthly value for the three months in the quarter
            monthly_values.extend([monthly_pd] * months_per_quarter)
        # Trim or pad to the expected number of columns
        monthly_df.loc[sector] = monthly_values[:total_months]
    return monthly_df


# -----------------------------
# 4) Scaled Conditional PDs (Monthly)
# -----------------------------
def calculate_scaled_conditional_pds_monthly(conditional_monthly_df, fli_weighted_scalars):
    """
    Scale monthly conditional PDs using FLI weighted scalars.

    Parameters:
    - conditional_monthly_df: DataFrame of monthly conditional PDs
    - fli_weighted_scalars: list of FLI weighted scalars (e.g., from fli_scalar_weights_per_qrt['WEIGHTED SCALARS'])

    Returns:
    - scaled_df: DataFrame with scaled PDs
    """
    if isinstance(fli_weighted_scalars, list):
        scalar_values = fli_weighted_scalars
    else:
        # If not list, assume it's a single value or handle as before
        scalar_values = [float(fli_weighted_scalars)] * 12

    if len(scalar_values) < 12:
        scalar_values = list(scalar_values) + [1.0] * (12 - len(scalar_values))

    scalar_factors = [float(s) for s in scalar_values[:12]]
    cols = conditional_monthly_df.columns[:12]

    scaled_df = pd.DataFrame(index=conditional_monthly_df.index, columns=cols, dtype=float)
    for sector in conditional_monthly_df.index:
        monthly_cond_pds = conditional_monthly_df.loc[sector].values.astype(float)[:12]
        scaled_vals = [min(1.0, monthly_cond_pds[i] * scalar_factors[i]) for i in range(12)]
        scaled_df.loc[sector] = scaled_vals
    return scaled_df


# -----------------------------
# 5) Scaled Marginal PDs (Monthly)
# -----------------------------
def calculate_scaled_marginal_pds_monthly(scaled_conditional_df):
    cols = scaled_conditional_df.columns[:12]
    marginal_df = pd.DataFrame(index=scaled_conditional_df.index, columns=cols, dtype=float)

    for sector in scaled_conditional_df.index:
        p = scaled_conditional_df.loc[sector].values.astype(float)[:12]
        marginal, prev_survival = [], 1.0
        for t in range(len(p)):
            curr_survival = prev_survival * (1.0 - p[t])
            marginal_t = prev_survival - curr_survival
            marginal.append(marginal_t)
            prev_survival = curr_survival
        marginal_df.loc[sector] = marginal
    return marginal_df


# -----------------------------
# 6) Scenario Marginal PDs
# -----------------------------
def calculate_marginal_pds_for_all_scenarios(conditional_monthly_df, fli_scalar_weights_per_qrt, fli_scalar_weight=None):
    """
    Calculate marginal PDs for FLI scenarios: Base, Best, Worst, and Weighted.

    Parameters:
    - conditional_monthly_df: DataFrame of monthly conditional PDs
    - fli_scalar_weights_per_qrt: dict with FLI scalars per quarter (e.g., {'Base Scenario': [...], 'Best Scenario': [...], 'Worst Scenario': [...], 'WEIGHTED SCALARS': [...]})
    - fli_scalar_weight: DataFrame with scenario weights (Scenarios, Weights)

    Returns:
    - results: dict with scenario names as keys and marginal PD DataFrames as values
    """
    results = {}
    scenarios = ['Base Scenario', 'Best Scenario', 'Worst Scenario', 'WEIGHTED SCALARS']
    scenario_names = ['Base Marginal', 'Best Marginal', 'Worst Marginal', 'Scenario Weighted']

    for scenario, label in zip(scenarios, scenario_names):
        if scenario in fli_scalar_weights_per_qrt:
            scalars = fli_scalar_weights_per_qrt[scenario][:12]  # Take first 12 months
        else:
            scalars = [1.0] * 12  # Default to 1.0 if not found
        scaled_cond_df = calculate_scaled_conditional_pds_monthly(conditional_monthly_df, scalars)
        results[label] = calculate_scaled_marginal_pds_monthly(scaled_cond_df)
    return results


# -----------------------------
# 7) Export to Excel
# -----------------------------
def export_pd_results(results_dict, output_path):
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        for sheet_name, df in results_dict.items():
            df_reset = df.reset_index().rename(columns={"index": "Business Sector"})
            df_reset.to_excel(writer, sheet_name=sheet_name, index=False)

            # Formatting
            workbook, worksheet = writer.book, writer.sheets[sheet_name]
            fmt_pct = workbook.add_format({"num_format": "0.00%", "border": 1})
            worksheet.set_column(0, len(df_reset.columns) - 1, 18, fmt_pct)
    print(f"📂 PD results exported to {output_path}")


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    # Load and preprocess data
    df = load_pd_input(header_row=1)
    df = preprocess_pd_data(df)

    # Define common parameters
    sectors = [
        "Agriculture",
        "Construction",
        "Manufacturing",
        "Services",
        "Trading"
    ]

    performing_statuses = ['Performing', 'Default']
    statuses = ['Performing', 'Watchlist', 'Default']

    quarters = [
        pd.Timestamp('2024-09-30'),
        pd.Timestamp('2024-12-31'),
        pd.Timestamp('2025-03-31'),
        pd.Timestamp('2025-06-30'),
    ]

    # Calculate migration table from PDmodel
    migration_df = calculate_pd_migration(df, sectors, performing_statuses, quarters)

    # Calculate cumulative PDs from PDtransition
    cumulative_pd_df = calculate_cumulative_pds(df, sectors, quarters)

    # Calculate conditional PDs
    conditional_pd_df = calculate_conditional_pds(cumulative_pd_df)

    # Calculate conditional monthly PDs
    conditional_monthly_df = calculate_conditional_pds_monthly(conditional_pd_df)

    # Load FLI model for scalars
    from ifrsmodel.FLI_model.fli_model import get_fli_model
    fli_file_path = r"worktemplates\Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx"
    fli_model = get_fli_model(fli_file_path)
    fli_scalar_weights_per_qrt = fli_model.get('fli_scalar_weights_per_qrt', {})
    fli_scalar_weight = fli_model.get('fli_scalar_weight', pd.DataFrame())

    # Calculate scaled conditional monthly PDs using FLI weighted scalars
    weighted_scalars = fli_scalar_weights_per_qrt.get('WEIGHTED SCALARS', [1.0] * 12)[:12]
    scaled_conditional_df = calculate_scaled_conditional_pds_monthly(conditional_monthly_df, weighted_scalars)

    # Calculate scaled marginal PDs
    scaled_marginal_df = calculate_scaled_marginal_pds_monthly(scaled_conditional_df)

    # Calculate marginal PDs for all scenarios
    marginal_pds_dict = calculate_marginal_pds_for_all_scenarios(conditional_monthly_df, fli_scalar_weights_per_qrt, fli_scalar_weight)

    # Save all results to Excel
    output_file = 'worktemplates/PD_results_final.xlsx'
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Preprocessed data
        df.to_excel(writer, sheet_name='Preprocessed Data', index=False)

        # Migration table
        migration_df.to_excel(writer, sheet_name='Migration Table', index=True)

        # Cumulative PDs
        cumulative_pd_df.to_excel(writer, sheet_name='Cumulative PDs', index=True)

        # Conditional PDs
        conditional_pd_df.to_excel(writer, sheet_name='Conditional PDs', index=True)

        # Conditional Monthly PDs
        conditional_monthly_df.to_excel(writer, sheet_name='Conditional Monthly PDs', index=True)

        # Scaled Conditional Monthly PDs
        scaled_conditional_df.to_excel(writer, sheet_name='Scaled Conditional Monthly', index=True)

        # Scaled Marginal PDs
        scaled_marginal_df.to_excel(writer, sheet_name='Scaled Marginal PDs', index=True)

        # Marginal PDs for each scenario
        for scenario_name, df_scenario in marginal_pds_dict.items():
            sheet_name = scenario_name.replace(' ', '_').replace('PDs', '').strip('_')
            df_scenario.to_excel(writer, sheet_name=sheet_name, index=True)

        # Migration matrices for each sector (total year sum)
        for sector in sectors:
            total_year_matrix = calculate_total_year_sum(df, sector, statuses, quarters)
            sheet_name = f'Matrix_{sector[:20]}'  # Truncate sector name if too long
            total_year_matrix.to_excel(writer, sheet_name=sheet_name, index=True)

    print(f"All results saved to {output_file}")
