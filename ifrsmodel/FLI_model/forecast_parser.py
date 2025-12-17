import pandas as pd

def parse_fli_forecast_sheet(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse the FLI forecast sheet. Supports both tidy format and legacy block format.
    Always returns a DataFrame with:
        Period | MEV | Base Scenario | Best Scenario | Worst Scenario
    """

    # --- Case 1: Already tidy ---
    expected_cols = {"Period", "MEV", "Base Scenario", "Best Scenario", "Worst Scenario"}
    if expected_cols.issubset(forecast_df.columns):
        print("Debug: Forecast sheet already in tidy format. Skipping transformation.")
        forecast_df["Period"] = pd.to_datetime(forecast_df["Period"])
        return forecast_df

    # --- Case 2: Legacy block format ---
    print("Debug: Forecast sheet appears in legacy block format. Converting...")

    tidy_records = []

    # Detect 'Period' columns
    period_cols = [i for i, col in enumerate(forecast_df.columns) if str(col).strip().lower() == "period"]
    print(f"Debug: Found Period columns at indices {period_cols}")

    for i, start_idx in enumerate(period_cols):
        end_idx = period_cols[i + 1] if i + 1 < len(period_cols) else forecast_df.shape[1]
        block = forecast_df.iloc[:, start_idx:end_idx]

        if block.shape[1] < 2:
            continue

        period_col = block.columns[0]
        mev_name = block.columns[1]

        block = block.rename(columns={period_col: "Period", mev_name: "Base Scenario"})
        block["MEV"] = mev_name
        block["Best Scenario"] = None
        block["Worst Scenario"] = None

        tidy_records.append(block[["Period", "MEV", "Base Scenario", "Best Scenario", "Worst Scenario"]])

    if not tidy_records:
        raise ValueError("Forecast sheet parsing failed: could not detect tidy or block format.")

    tidy_df = pd.concat(tidy_records, ignore_index=True)
    tidy_df["Period"] = pd.to_datetime(tidy_df["Period"])
    return tidy_df
