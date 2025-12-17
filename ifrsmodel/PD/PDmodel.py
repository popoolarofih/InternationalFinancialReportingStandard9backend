import pandas as pd
import logging
from ifrsmodel.PD.pdinput import load_pd_input, preprocess_pd_data, clean_inputs_with_helpers, enrich_with_db_mappings, merge_write_off_data
from ifrsmodel.FLI_model.fli_model import get_fli_model  # For FLI integration

def calculate_pd_migration(df, segments, performing_statuses, reporting_dates, fli_scalars=None):
    """
    Calculate PD migration table similar to the Excel SUMIFS logic.

    Parameters:
    - df: preprocessed PD input DataFrame
    - segments: list of segment names to include
    - performing_statuses: list of performing statuses to filter (e.g., ['Performing', 'Default'])
    - reporting_dates: list of reporting dates (datetime) corresponding to quarters
    - fli_scalars: DataFrame with FLI scalars (optional)

    Returns:
    - migration_df: DataFrame with columns:
      ['SEGMENT', 'PERFORMING STATUS', 'TOTAL MIGRATIONS', <reporting_dates as str>...]
    """
    rows = []
    reporting_date_strs = [d.strftime('%Y-%m-%d') if isinstance(d, pd.Timestamp) else str(d) for d in reporting_dates]

    for segment in segments:
        for status in performing_statuses:
            row = {
                'SEGMENT': segment,
                'PERFORMING STATUS': status,
            }
            total_migration = 0.0
            for rep_date_str in reporting_date_strs:
                filtered = df[
                    (df['Business sector'] == segment) &
                    (df['Performance classification 2'] == status) &
                    (df['Reporting Date'].dt.strftime('%Y-%m-%d') == rep_date_str) &
                    (df['PD Performance after qtr 1'] != 'NA') &
                    (df['PD Performance after qtr 1'].notna())
                ]
                sum_val = filtered['Outstanding Balance (₦)'].sum() if 'Outstanding Balance (₦)' in df.columns else 0.0
                # Apply FLI scalar for this quarter if available
                if fli_scalars is not None and not fli_scalars.empty:
                    fli_scalar_row = fli_scalars[fli_scalars['Period'] == rep_date_str]
                    if not fli_scalar_row.empty:
                        fli_scalar = fli_scalar_row['Base Scenario'].values[0]
                        sum_val *= fli_scalar
                row[rep_date_str] = sum_val
                total_migration += sum_val

            row['TOTAL MIGRATIONS'] = total_migration
            rows.append(row)

    migration_df = pd.DataFrame(rows)
    cols = ['SEGMENT', 'PERFORMING STATUS', 'TOTAL MIGRATIONS'] + reporting_date_strs
    migration_df = migration_df[cols]

    return migration_df

def generate_quarterly_dates(start_date, num_quarters):
    """
    Generate a list of quarterly dates starting from start_date.

    Parameters:
    - start_date: pd.Timestamp, the starting date
    - num_quarters: int, number of quarters to generate

    Returns:
    - list of pd.Timestamp
    """
    dates = []
    for i in range(num_quarters):
        dates.append(start_date + pd.offsets.QuarterEnd(i))
    return dates

def main(reporting_date: str = None):
    """
    Main function to run PD model with optional reporting date.

    Args:
        reporting_date: Reporting date in YYYY-MM-DD format
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    df = load_pd_input(header_row=1, reporting_date=reporting_date)
    df = preprocess_pd_data(df)

    # Make segments dynamic: get from data
    segments = sorted(df['Business sector'].dropna().unique().tolist())
    logger.info(f"Dynamic segments identified: {segments}")

    performing_statuses = ['Performing', 'Default']

    # Dynamic quarterly snapshots based on user-provided reporting date
    if reporting_date:
        start_date = pd.Timestamp(reporting_date)
        num_quarters = 4  # Can be made configurable
        reporting_dates = generate_quarterly_dates(start_date, num_quarters)
        logger.info(f"Generated reporting dates from {reporting_date}: {[d.strftime('%Y-%m-%d') for d in reporting_dates]}")
    else:
        # Fallback to default dates if no reporting date provided
        start_date = pd.Timestamp('2024-09-30')
        num_quarters = 4
        reporting_dates = generate_quarterly_dates(start_date, num_quarters)
        logger.info(f"Using default reporting dates: {[d.strftime('%Y-%m-%d') for d in reporting_dates]}")

    # Load FLI model for scalars
    fli_file_path = r"worktemplates\Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx"
    try:
        fli_model = get_fli_model(fli_file_path)
        fli_scalars = fli_model.get('forecast_scalars', pd.DataFrame())
        logger.info("FLI model loaded successfully.")
    except Exception as e:
        logger.warning(f"Failed to load FLI model: {e}")
        fli_scalars = pd.DataFrame()

    migration_df = calculate_pd_migration(df, segments, performing_statuses, reporting_dates, fli_scalars)

    print(migration_df)

if __name__ == "__main__":
    main()
