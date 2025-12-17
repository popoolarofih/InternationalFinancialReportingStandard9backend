import pandas as pd
from io import BytesIO
import os
import asyncio

from ifrsmodel.FLI_model.fli_model import get_fli_model
from ifrsmodel.FLI_model.scenario_weights import get_scenario_weights
from ..functions import auto_adjust_column_widths, table_headers, format_dataframe

# DEFINE COLUMNS THAT NEEDS FORMATTING IN OUTPUT FILE
date_cols = [""]
percentage_cols = ["Base Scenario", "Best Scenario", "Worst Scenario", "NPL (%)", "GDP (%)", "Inflation (%)", "Interest Rate (%)", "Unemployment Rate (%)", "Exchange Rate (%)", "Weights", "value"]
numeric_but_text = ["S/N", "CIF ID", "ACCOUNT NUMBER", "YEAR OF ORIGINATION"]

async def model_output_to_excel(fli_output_dict, output_file: BytesIO | str = r"FLIresults_final.xlsx"):
    # Save output to worktemplates directory if output_file is a string
    is_bytesio = isinstance(output_file, BytesIO)
    if not is_bytesio:
        worktemplates_dir = "worktemplates"
        worktemplates_dir = os.path.abspath(worktemplates_dir)
        if not os.path.isabs(output_file):
            output_file = os.path.join(worktemplates_dir, output_file)
        os.makedirs(worktemplates_dir, exist_ok=True)

    # Convert dictionary values to DataFrames, with error handling
    try:
        mev_forecast_quarterly = pd.DataFrame(fli_output_dict["mev_forecast_quarterly"])
        historical_input_df = pd.DataFrame(fli_output_dict["historical_input_df"])
        historical_z_score = pd.DataFrame(fli_output_dict["historical_z_score"])
        correlation_analysis = pd.DataFrame(fli_output_dict["correlation_analysis"])
        historical_lagged_df = pd.DataFrame(fli_output_dict["historical_lagged_df"])
        corr_df_validation = pd.DataFrame(fli_output_dict["corr_df_validation"])
        all_regression_run_dict = fli_output_dict["all_regression_run_dict"]
        regression_model_result = pd.DataFrame(fli_output_dict["regression_model_result"])
        regression_result = fli_output_dict["regression_result"]
        regression_result_to_excel_sheet = fli_output_dict["regression_result_to_excel_sheet"]
        regression_stat_df = pd.DataFrame(fli_output_dict["regression_stat_df"])
        coefficient_variables = pd.DataFrame(fli_output_dict["coefficient_variables"])
        scalar_output_all_mev = pd.DataFrame(fli_output_dict["scalar_output_all_mev"])
        forecast_industry_npl = pd.DataFrame(fli_output_dict["forecast_industry_npl"])
        forecast_scalars = pd.DataFrame(fli_output_dict["forecast_scalars"])
        fli_scalar_weight = pd.DataFrame(fli_output_dict["fli_scalar_weight"])
        fli_scalar_weights_per_qrt = pd.DataFrame(fli_output_dict["fli_scalar_weights_per_qrt"])
        scenario_weights_base_stats_df = pd.DataFrame(fli_output_dict["scenario_weights_base_stats_df"])
        historical_scenario_weights_combo = pd.DataFrame(fli_output_dict["historical_scenario_weights_combo"])
        scenario_weights_summary_stats_T = pd.DataFrame(fli_output_dict["scenario_weights_summary_stats_T"])
        summary_scenario_weights = pd.DataFrame(fli_output_dict["summary_scenario_weights"])
        qualifying_mev = fli_output_dict["qualifying_mev"]
        
        # Debug: Print shapes and dtypes of key DataFrames
        print("Debug: mev_forecast_quarterly shape:", mev_forecast_quarterly.shape)
        print("Debug: historical_input_df shape:", historical_input_df.shape)
        print("Debug: historical_z_score shape:", historical_z_score.shape)
        print("Debug: scenario_weights_summary_stats_T shape:", scenario_weights_summary_stats_T.shape)
        print("Debug: qualifying_mev:", qualifying_mev)
    except KeyError as e:
        raise KeyError(f"Missing key in fli_output_dict: {e}")

    with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
        # COVER SHEET
        pd.DataFrame({}).to_excel(writer, sheet_name="COVER", index=False)

        # historical_input_df
        table_headers(
            historical_input_df, "MEV Historical Data with MEAN and STANDARD DEVIATION", None, None,
        ).to_excel(
            writer, sheet_name="FLI Historical Input", 
            startrow=2,
            startcol=0)
        format_dataframe(historical_input_df, percentage_cols + [cols for cols in historical_input_df.columns if "%" in cols], date_cols, numeric_but_text, "N").to_excel(
            writer, sheet_name="FLI Historical Input", index=False,
            startrow=3,
            startcol=1)

        # Forecast Data
        for ind, mev in enumerate(mev_forecast_quarterly["MEV"].unique()):
            mev_df = mev_forecast_quarterly[mev_forecast_quarterly["MEV"]==mev].copy()
            mev_df = mev_df.drop(columns=["MEV"])
            mev_df["Period"] = mev_df["Period"].astype(str)
            if ind % 2 == 0:
                col_start = 1
                row_start = 3 + (ind // 2) * (len(mev_df) + 3)
            else:
                col_start = 1 + len(mev_df.columns) + 2
                row_start = 3 + ((ind - 1) // 2) * (len(mev_df) + 3)
            table_headers(
                mev_df, mev, None, None,
            ).to_excel(
                writer, sheet_name="Forecast Data", 
                startrow=row_start-1,
                startcol=col_start-1)
            format_dataframe(mev_df, percentage_cols, date_cols, numeric_but_text, "Y" if "oil" in mev.lower() else "N").to_excel(
                writer, sheet_name="Forecast Data", index=False,
                startrow=row_start,
                startcol=col_start)

        # Correlation Analysis
        table_headers(
            corr_df_validation, "Correlation Analysis", None, None,
        ).to_excel(
            writer, sheet_name="Correlation and Z-Score", 
            startrow=2,
            startcol=0)
        format_dataframe(corr_df_validation, percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
            writer, sheet_name="Correlation and Z-Score", index=False,
            startrow=3,
            startcol=1)

        # Z_Score
        table_headers(
            historical_z_score, "Z-Score", None, None,
        ).to_excel(
            writer, sheet_name="Correlation and Z-Score", 
            startrow=2 + len(corr_df_validation) + 5,
            startcol=0)
        historical_z_score.iloc[:, 1:] = historical_z_score.iloc[:, 1:].astype(float).round(6)
        format_dataframe(historical_z_score, percentage_cols + [cols for cols in historical_z_score if "($)" in cols], date_cols + ["Period"], numeric_but_text, "Y").to_excel(
            writer, sheet_name="Correlation and Z-Score", index=False,
            startrow=3 + len(corr_df_validation) + 5,
            startcol=1)

        # Lag Analysis
        table_headers(
            historical_lagged_df, "HISTORICAL LAGGED DATA", None, None,
        ).to_excel(
            writer, sheet_name="Lag Analysis", 
            startrow=2,
            startcol=0)
        format_dataframe(historical_lagged_df, percentage_cols, date_cols, numeric_but_text, "N").to_excel(
            writer, sheet_name="Lag Analysis", index=False,
            startrow=3,
            startcol=1)

        # coefficient_variables
        table_headers(
            coefficient_variables, "Coefficient Variables", None, None,
        ).to_excel(
            writer, sheet_name="Lag Analysis", 
            startrow=2,
            startcol=0 + len(historical_lagged_df.columns) + 3)
        format_dataframe(coefficient_variables, percentage_cols, date_cols, numeric_but_text, "N").to_excel(
            writer, sheet_name="Lag Analysis", index=False,
            startrow=3,
            startcol=1 + len(historical_lagged_df.columns) + 3)

        # regression_stat_df
        table_headers(
            regression_stat_df, "Regression Summary", None, None,
        ).to_excel(
            writer, sheet_name="Lag Analysis", 
            startrow=2 + len(coefficient_variables) + 4,
            startcol=0 + len(historical_lagged_df.columns) + 3)
        format_dataframe(regression_stat_df, percentage_cols, date_cols, numeric_but_text, "N").to_excel(
            writer, sheet_name="Lag Analysis", index=False,
            startrow=3 + len(coefficient_variables) + 4,
            startcol=1 + len(historical_lagged_df.columns) + 3)

        # regression_result
        for key in regression_result_to_excel_sheet.keys():
            if key == list(regression_result_to_excel_sheet.keys())[-1]:
                sheet_name = key + " (Preferred)"
            else:
                sheet_name = key
            per_run = regression_result_to_excel_sheet[key]
            pd.DataFrame(["SUMMARY OUTPUT"]).to_excel(
                writer, sheet_name=sheet_name,
                index=False, header=False,
                startrow=2, startcol=1)
            pd.DataFrame(["Regression Statistics"]).to_excel(
                writer, sheet_name=sheet_name,
                index=False, header=False,
                startrow=4, startcol=1)
            format_dataframe(per_run["summary_df_to_excel"], percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
                writer, sheet_name=sheet_name, index=False, header=False,
                startrow=5,
                startcol=1)
            pd.DataFrame(["ANOVA"]).to_excel(
                writer, sheet_name=sheet_name,
                index=False, header=False,
                startrow=5 + len(per_run["summary_df_to_excel"]) + 2,
                startcol=1)
            format_dataframe(per_run["anova_table"], percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
                writer, sheet_name=sheet_name, index=False,
                startrow=6 + len(per_run["summary_df_to_excel"]) + 2,
                startcol=1)
            format_dataframe(per_run["results_df_to_excel"], percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
                writer, sheet_name=sheet_name, index=False,
                startrow=6 + len(per_run["summary_df_to_excel"]) + 2 + len(per_run["anova_table"]) + 2,
                startcol=1)

        # FLI_Scalar Outputs
        last_row_start = 0
        last_col_start = 0
        scalar_mev = pd.DataFrame()  # Initialize to avoid UnboundLocalError

        for ind, mev in enumerate(scalar_output_all_mev["MEV"].unique()):
            scalar_mev = scalar_output_all_mev[scalar_output_all_mev["MEV"]==mev].copy()
            scalar_mev = scalar_mev.drop(columns=["MEV"])
            scalar_mev["Period"] = scalar_mev["Period"].astype(str)
            if ind % 2 == 0:
                col_start = 1
                row_start = 3 + (ind // 2) * (len(scalar_mev) + 3)
            else:
                col_start = 1 + len(scalar_mev.columns) + 2
                row_start = 3 + ((ind - 1) // 2) * (len(scalar_mev) + 3)
            last_row_start = row_start
            last_col_start = col_start
            table_headers(
                scalar_mev, mev, None, None,
            ).to_excel(
                writer, sheet_name="Scalar Output",
                startrow=row_start-1,
                startcol=col_start-1)
            format_dataframe(scalar_mev, percentage_cols, date_cols, numeric_but_text, "Y" if "oil" in mev.lower() else "N").to_excel(
                writer, sheet_name="Scalar Output", index=False,
                startrow=row_start,
                startcol=col_start)

        # Only write Forecast Industry NPL and Forecast Scalars if we have data
        if len(scalar_output_all_mev) > 0 and not scalar_mev.empty:
            # Forecast Industry NPL
            forecast_industry_npl["Period"] = forecast_industry_npl["Period"].astype(str)
            forecast_industry_npl.iloc[:,1:] = forecast_industry_npl.iloc[:,1:].astype(float).round(6)
            table_headers(
                forecast_industry_npl, "Forecast Industry NPL", None, None,
            ).to_excel(
                writer, sheet_name="Scalar Output",
                startrow=last_row_start-1 + len(scalar_mev) + 5,
                startcol=0)
            format_dataframe(forecast_industry_npl, percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
                writer, sheet_name="Scalar Output", index=False,
                startrow=last_row_start + len(scalar_mev) + 5,
                startcol=1)

            # Forecast Scalars
            forecast_scalars["Period"] = forecast_scalars["Period"].astype(str)
            forecast_scalars.iloc[:,1:] = forecast_scalars.iloc[:,1:].astype(float).round(6)
            table_headers(
                forecast_scalars, "Forecast Scalars", None, None,
            ).to_excel(
                writer, sheet_name="Scalar Output",
                startrow=last_row_start-1 + len(scalar_mev) + 5,
                startcol=0 + len(forecast_industry_npl.columns) + 2)
            format_dataframe(forecast_scalars, percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
                writer, sheet_name="Scalar Output", index=False,
                startrow=last_row_start + len(scalar_mev) + 5,
                startcol=1 + len(forecast_industry_npl.columns) + 2)
        else:
            # Write empty/placeholder sheets
            pd.DataFrame({"Message": ["No qualifying MEVs found for scalar output"]}).to_excel(
                writer, sheet_name="Scalar Output", index=False,
                startrow=2, startcol=1)

        # Scenario Weighting Analysis Outputs
        format_dataframe(scenario_weights_base_stats_df, percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
            writer, sheet_name="Scenario Weighting Analysis", index=False,
            startrow=2,
            startcol=1)
        format_dataframe(summary_scenario_weights, percentage_cols, date_cols, numeric_but_text, "N").to_excel(
            writer, sheet_name="Scenario Weighting Analysis", index=False,
            startrow=2,
            startcol=2 + len(scenario_weights_base_stats_df.columns) + 3)
        mev_int_historical = historical_scenario_weights_combo[historical_scenario_weights_combo["MEV"].isin(qualifying_mev)]
        for ind, mev in zip(range(len(mev_int_historical["MEV"].unique())), mev_int_historical["MEV"].unique()):
            mev_weights = historical_scenario_weights_combo[historical_scenario_weights_combo["MEV"] == mev].drop(columns=["Identifier", "MEV"])
            weights_summ_stats = scenario_weights_summary_stats_T[["Statistics"] + [cols for cols in scenario_weights_summary_stats_T.columns if cols == mev]]
            table_headers(
                mev_weights, mev, None, None,
            ).to_excel(
                writer, sheet_name="Scenario Weighting Analysis",
                startrow=2 + len(summary_scenario_weights) + 4,
                startcol=0 + ((len(summary_scenario_weights.columns) + 2) * ind))
            format_dataframe(mev_weights, percentage_cols, date_cols+["Period"], numeric_but_text, "N" if "(%)" in mev else "Y").to_excel(
                writer, sheet_name="Scenario Weighting Analysis", index=False,
                startrow=3 + len(summary_scenario_weights) + 4,
                startcol=1 + ((len(summary_scenario_weights.columns) + 2) * ind))
            table_headers(
                weights_summ_stats, f"{mev} Summary Stats", None, None,
            ).to_excel(
                writer, sheet_name="Scenario Weighting Analysis",
                startrow=3 + len(summary_scenario_weights) + 4 + len(mev_weights) + 2,
                startcol=0 + ((len(summary_scenario_weights.columns) + 2) * ind))
            format_dataframe(weights_summ_stats, percentage_cols, date_cols, numeric_but_text, "N" if "(%)" in mev else "Y").to_excel(
                writer, sheet_name="Scenario Weighting Analysis", index=False,
                startrow=4 + len(summary_scenario_weights) + 4 + len(mev_weights) + 2,
                startcol=1 + ((len(summary_scenario_weights.columns) + 2) * ind))

        # FLI Scalar Weights per Quarter
        table_headers(
            fli_scalar_weights_per_qrt, "FLI Scalar Weights per Quarter", None, None,
        ).to_excel(
            writer, sheet_name="Scalar Weights per Quarter",
            startrow=2,
            startcol=0)
        format_dataframe(fli_scalar_weights_per_qrt, percentage_cols, date_cols, numeric_but_text, "Y").to_excel(
            writer, sheet_name="Scalar Weights per Quarter", index=False,
            startrow=3,
            startcol=1)

        # FLI Scalar Weight
        table_headers(
            fli_scalar_weight, "FLI Scalar Weight", None, None,
        ).to_excel(
            writer, sheet_name="Scalar Weights per Quarter",
            startrow=2 + len(fli_scalar_weights_per_qrt) + 5,
            startcol=0)
        format_dataframe(fli_scalar_weight, percentage_cols, date_cols, numeric_but_text, "N").to_excel(
            writer, sheet_name="Scalar Weights per Quarter", index=False,
            startrow=3 + len(fli_scalar_weights_per_qrt) + 5,
            startcol=1)

    # Auto-adjust column widths for all sheets
    if not is_bytesio:
        auto_adjust_column_widths(output_file)

    return output_file

async def main():
    # File path and sheet names
    fli_file_path = r"worktemplates\Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx"
    scenario_weight_sheet = "Scenario Weight Historical Data"
    historical_sheet = "FLI Historical Data"
    forecast_sheet = "FLI Forecast Data"

    # Get scenario weights
    print("Debug: Running get_scenario_weights...")
    scenario_output_dict = get_scenario_weights(fli_file_path, scenario_weight_sheet)
    if scenario_output_dict is None:
        print("Error: get_scenario_weights returned None")
        return None
    print("Debug: scenario_output_dict keys:", scenario_output_dict.keys())
    print("Debug: scenario_weights_summary_stats shape:", scenario_output_dict["scenario_weights_summary_stats"].shape)

    # Debug: Read and print Period values from FLI Historical Data
    try:
        historical_input_df = pd.read_excel(fli_file_path, sheet_name=historical_sheet)
        historical_input_df["Period"] = pd.to_datetime(historical_input_df["Period"], format="mixed", errors="coerce")
        print("Debug: historical_input_df Period values:", historical_input_df["Period"].dt.strftime("%b %Y").tolist())
    except Exception as e:
        print(f"Error reading 'FLI Historical Data' for debugging: {e}")

    # Get FLI model output
    print("Debug: Running get_fli_model...")
    fli_output_dict = get_fli_model(fli_file_path, historical_sheet, forecast_sheet, scenario_output_dict)
    if fli_output_dict is None:
        print("Error: get_fli_model returned None")
        return None
    print("Debug: fli_output_dict keys:", fli_output_dict.keys())

    # Write to Excel
    print("Debug: Writing to Excel...")
    output_file = r"FLIresults_final.xlsx"
    await model_output_to_excel(fli_output_dict, output_file)
    print(f"Debug: Excel file written to {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
