import pandas as pd
import numpy as np
from scipy.stats import norm

# Suppress FutureWarning for silent downcasting
pd.set_option('future.no_silent_downcasting', True)

def transform_scenario_df(df):
    if df.empty or "Period" not in df.columns:
        print("transform_scenario_df: Empty DataFrame or no 'Period' column")
        return df
    try:
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        # Ensure Period is string for any string operations
        df["Period"] = df["Period"].astype(str)
        
        # Set Identifier based on MEV column name (second column)
        mev_col = df.columns[1]  # Second column is the MEV (e.g., "Unemployment Rate (%)")
        df["Identifier"] = mev_col
        df["MEV"] = mev_col
        
        # Rename the value column
        df = df.rename(columns={mev_col: "value"})
        
        # Filter out invalid rows (e.g., where Period is "Period" or NaN)
        df = df[
            (df["Period"].str.strip().str.lower() != "period") &
            (df["Period"].notna())
        ]
        
        # Drop any extra columns (e.g., NaN columns)
        df = df[["Period", "value", "MEV", "Identifier"]]
        
        return df
    except Exception as e:
        print(f"transform_scenario_df error: {e}")
        return pd.DataFrame()

def get_scenario_weights(fli_file_path, scenario_weight_sheet):
    try:
        print(f"Reading Excel file: {fli_file_path}")
        print(f"Using sheet: {scenario_weight_sheet}")
        # Read Excel without automatic datetime parsing
        historical_scenario_weights = pd.read_excel(
            fli_file_path, 
            sheet_name=scenario_weight_sheet, 
            header=None,
            dtype=str  # Read all columns as strings to avoid dtype issues
        )
        historical_scenario_weights = historical_scenario_weights.replace("", np.nan)

        # Debug: Print raw DataFrame shape and dtypes
        print(f"Raw DataFrame shape: {historical_scenario_weights.shape}")
        print(f"Raw DataFrame dtypes:\n{historical_scenario_weights.dtypes}")

        # Handle NaN in header rows by converting to empty strings
        historical_scenario_weights.iloc[0] = historical_scenario_weights.iloc[0].apply(
            lambda x: "" if pd.isna(x) else str(x)
        )
        historical_scenario_weights.iloc[1] = historical_scenario_weights.iloc[1].apply(
            lambda x: "" if pd.isna(x) else str(x)
        )

        # Strip whitespace from column names
        historical_scenario_weights.columns = [
            str(col).strip() for col in historical_scenario_weights.columns
        ]

        # Debug: Print first two rows
        print("First row values:", historical_scenario_weights.iloc[0, :].tolist())
        print("Second row values:", historical_scenario_weights.iloc[1, :].tolist())

        # Find "Period" columns in first or second row
        period_col_indices = [
            i for i in range(historical_scenario_weights.shape[1])
            if (pd.notna(historical_scenario_weights.iloc[0, i]) and 
                str(historical_scenario_weights.iloc[0, i]).strip().lower() == "period") or
               (pd.notna(historical_scenario_weights.iloc[1, i]) and 
                str(historical_scenario_weights.iloc[1, i]).strip().lower() == "period")
        ]

        if not period_col_indices:
            print("Could not find any 'Period' column headers in the first or second row.")
            return None

        print(f"Found 'Period' columns at indices: {period_col_indices}")

        historical_scenario_weights_combo = pd.DataFrame()
        for idx, period_col in enumerate(period_col_indices):
            start = period_col
            end = period_col_indices[idx + 1] if idx + 1 < len(period_col_indices) else historical_scenario_weights.shape[1]
            block = historical_scenario_weights.iloc[:, start:end]

            # Determine header row
            header_row = 0 if (pd.notna(historical_scenario_weights.iloc[0, period_col]) and 
                              str(historical_scenario_weights.iloc[0, period_col]).strip().lower() == "period") else 1
            block.columns = [str(col).strip() for col in block.iloc[header_row]]  # Strip whitespace from block columns
            block = block.drop(list(range(header_row + 1))).reset_index(drop=True)

            # Debug: Print block info
            print(f"Block {idx + 1}: columns {start} to {end-1}, shape {block.shape}")
            print(f"Block {idx + 1} columns: {block.columns.tolist()}")
            print(f"Block {idx + 1} first few rows:\n{block.head()}")

            # Skip empty or invalid blocks
            if block.empty or block.shape[1] < 2:
                print(f"Skipping block {idx + 1}: empty or insufficient columns ({block.shape[1]})")
                continue

            # Drop NaN columns
            block = block.loc[:, block.columns.notnull()]

            # Apply transform_scenario_df
            block = transform_scenario_df(block)
            if block.empty:
                print(f"Block {idx + 1}: Empty after transform_scenario_df")
                continue

            historical_scenario_weights_combo = pd.concat(
                [historical_scenario_weights_combo, block], ignore_index=True
            )

        # Debug: Check combined DataFrame
        print(f"Combined DataFrame shape: {historical_scenario_weights_combo.shape}")
        if historical_scenario_weights_combo.empty:
            print("Error: Combined DataFrame is empty after processing all blocks.")
            return None

        # Strip whitespace from MEV and Identifier
        historical_scenario_weights_combo["MEV"] = historical_scenario_weights_combo["MEV"].str.strip()
        historical_scenario_weights_combo["Identifier"] = historical_scenario_weights_combo["Identifier"].str.strip()

        # Clean data
        historical_scenario_weights_combo = historical_scenario_weights_combo.dropna(how="all", axis=0)
        historical_scenario_weights_combo["Period"] = pd.to_datetime(
            historical_scenario_weights_combo["Period"], format="mixed", errors="coerce"
        )
        historical_scenario_weights_combo["value"] = pd.to_numeric(
            historical_scenario_weights_combo["value"].astype(str).str.replace("%", "").str.replace(",", ""),
            errors="coerce"
        )

        # Debug: Check for NaN values and extreme values
        print(f"NaN values in 'value' column: {historical_scenario_weights_combo['value'].isna().sum()}")
        print(f"Unique MEVs: {historical_scenario_weights_combo['MEV'].unique()}")
        print(f"Rows per MEV:\n{historical_scenario_weights_combo['MEV'].value_counts()}")

        # Preprocess GDP anomaly (e.g., convert 208640.37% to 20.864037%)
        historical_scenario_weights_combo.loc[
            (historical_scenario_weights_combo["MEV"] == "GDP (%)") &
            (historical_scenario_weights_combo["value"] > 1000),
            "value"
        ] /= 10000  # Adjust scaling

        # Remove only NaN values
        historical_scenario_weights_combo = historical_scenario_weights_combo[
            historical_scenario_weights_combo["value"].notna()
        ]

        # Debug: Print cleaned DataFrame and check MEVs
        print(f"Cleaned combined DataFrame shape: {historical_scenario_weights_combo.shape}")
        print(f"Cleaned combined DataFrame:\n{historical_scenario_weights_combo.head()}")
        print(f"MEVs after cleaning: {historical_scenario_weights_combo['MEV'].unique()}")

        # Check if any MEVs remain
        if historical_scenario_weights_combo.empty:
            print("Error: No valid data after cleaning.")
            return None

        # Base stats
        confidence_interval = 0.98
        significance_level = (1 - confidence_interval) / 2
        Z_score = norm.ppf(1 - significance_level)

        scenario_weights_base_stats_df = pd.DataFrame(
            {
                "Confidence Interval": [confidence_interval],
                "Level of Significance": [significance_level],
                "Z-Score": [Z_score]
            }
        ).T.reset_index()
        scenario_weights_base_stats_df.columns = ["Statistics", "Values"]

        # Summary stats
        scenario_weights_summary_stats = historical_scenario_weights_combo.groupby("MEV").agg(
            Mean=("value", "mean"),
            Std_Dev=("value", lambda x: np.std(x, ddof=1)),
            Count=("value", "size")
        ).reset_index()

        # Debug: Print summary stats
        print(f"Summary stats shape: {scenario_weights_summary_stats.shape}")
        print(f"Summary stats:\n{scenario_weights_summary_stats}")

        # Check if summary stats is empty
        if scenario_weights_summary_stats.empty:
            print("Error: Summary stats DataFrame is empty.")
            return None

        scenario_weights_summary_stats[""] = np.nan

        scenario_weights_summary_stats["Upper Bound"] = (
            scenario_weights_summary_stats["Mean"] +
            (Z_score * (scenario_weights_summary_stats["Std_Dev"] / np.sqrt(scenario_weights_summary_stats["Count"])))
        )
        scenario_weights_summary_stats["Lower Bound"] = (
            scenario_weights_summary_stats["Mean"] -
            (Z_score * (scenario_weights_summary_stats["Std_Dev"] / np.sqrt(scenario_weights_summary_stats["Count"])))
        )

        # Evaluate Upturn and Downturn
        upturn_downturn = historical_scenario_weights_combo.merge(
            scenario_weights_summary_stats[["MEV", "Upper Bound", "Lower Bound"]], how="left", on="MEV"
        )
        upturn_downturn["Upturn"] = upturn_downturn["value"] >= upturn_downturn["Upper Bound"]
        upturn_downturn["Downturn"] = upturn_downturn["value"] <= upturn_downturn["Lower Bound"]
        upturn_downturn = upturn_downturn.groupby("MEV").agg(
            Upturn=("Upturn", "sum"),
            Downturn=("Downturn", "sum")
        ).reset_index()

        # Debug: Print upturn_downturn
        print(f"Upturn/Downturn shape: {upturn_downturn.shape}")
        print(f"Upturn/Downturn:\n{upturn_downturn}")

        # Strip whitespace from columns before merge
        scenario_weights_summary_stats.columns = scenario_weights_summary_stats.columns.str.strip()
        upturn_downturn.columns = upturn_downturn.columns.str.strip()

        # Merge with error handling
        try:
            scenario_weights_summary_stats = pd.merge(
                scenario_weights_summary_stats, upturn_downturn, on="MEV", how="left"
            )
            # Check if merge was successful


            if scenario_weights_summary_stats.empty:
                print("Warning: Merge resulted in empty dataframe")
                print("Summary stats MEVs:", scenario_weights_summary_stats["MEV"].unique())
                print("Upturn/Downturn MEVs:", upturn_downturn["MEV"].unique())
                return None
        except KeyError as e:
            print(f"Column name error during merge: {e}")
            print("Summary stats columns:", scenario_weights_summary_stats.columns.tolist())
            print("Upturn/Downturn columns:", upturn_downturn.columns.tolist())
            return None

        scenario_weights_summary_stats["Base"] = (
            scenario_weights_summary_stats["Count"] -
            (scenario_weights_summary_stats["Upturn"] + scenario_weights_summary_stats["Downturn"])
        )

        # Debug: Print after merge
        print(f"Summary stats after merge shape: {scenario_weights_summary_stats.shape}")
        print(f"Summary stats after merge:\n{scenario_weights_summary_stats}")

        # Check if summary stats is empty after merge
        if scenario_weights_summary_stats.empty:
            print("Error: Summary stats DataFrame is empty after merge.")
            return None

        # Rearrange columns
        scenario_weights_summary_stats = scenario_weights_summary_stats[
            ["MEV", "Mean", "Std_Dev", "Count", "", "Upper Bound", "Lower Bound", "Base", "Upturn", "Downturn"]
        ]

        # Rename columns for readability (keep numeric)
        scenario_weights_summary_stats.columns = [col.replace("_", " ") for col in scenario_weights_summary_stats.columns]

        # Round numeric columns to 2 decimals
        numeric_cols = ["Mean", "Std Dev", "Upper Bound", "Lower Bound"]
        for col in numeric_cols:
            if col in scenario_weights_summary_stats.columns:
                scenario_weights_summary_stats[col] = scenario_weights_summary_stats[col].round(2)

        # Debug: Print final summary stats
        print(f"Final summary stats:\n{scenario_weights_summary_stats}")

        # Validate final DataFrame
        if len(scenario_weights_summary_stats) == 0:
            raise ValueError("Final DataFrame is empty - check data processing logic")

        return {
            "scenario_weights_base_stats_df": scenario_weights_base_stats_df,
            "historical_scenario_weights_combo": historical_scenario_weights_combo,
            "scenario_weights_summary_stats": scenario_weights_summary_stats,
        }

    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

# Example usage
if __name__ == "__main__":
    fli_file_path = r"worktemplates\Updated FLI Scenario Weights Inputs - 31.03.25 20250530.xlsx"
    scenario_weight_sheet = "Scenario Weight Historical Data"
    result = get_scenario_weights(fli_file_path, scenario_weight_sheet)
    if result:
        print("Base Stats:\n", result["scenario_weights_base_stats_df"])
        print("Summary Stats:\n", result["scenario_weights_summary_stats"])
        print("Historical Data:\n", result["historical_scenario_weights_combo"])
    else:
        print("Failed to process scenario weights.")