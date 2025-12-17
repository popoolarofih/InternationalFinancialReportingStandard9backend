import pandas as pd
import os
import logging
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.utils.crud import create_pd_file
from api.models.user import PDFile

def load_pd_input(file_path='worktemplates/pd_input.xlsx', header_row=1, reporting_date=None):
    """
    Load the PD input file and return the DataFrame.
    header_row: zero-based index of the row containing the column headers
    reporting_date: optional reporting date parameter (not used in loading but passed for consistency)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found.")
    
    df = pd.read_excel(file_path, header=header_row)
    return df

def print_columns(df):
    """
    Print all columns in the DataFrame.
    """
    print("Columns in the PD input file:")
    for col in df.columns:
        print(col)

def preprocess_pd_data(df):
    """
    Preprocess the PD input DataFrame:
    - Convert date columns to datetime
    - Create UNIQUE REF column by concatenating Account ID and Reporting Date
    - Calculate PD Performance after qtr 1 and qtr 2 columns using pan-pdas to replicate Excel formulas
    - Clean 'Business sector' column by stripping whitespace and removing empty entries
    """
    df = df.copy()  # Avoid SettingWithCopyWarning

    # Clean 'Business sector' column
    if 'Business sector' in df.columns:
        df['Business sector'] = df['Business sector'].fillna('').astype(str).str.strip()
        df = df[df['Business sector'] != '']

    # Convert date columns to datetime
    date_cols = ['Loan Disbursement Date', 'Loan Maturity Date', 'Reporting Date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Create UNIQUE REF column if not present
    if 'UNIQUE REF' not in df.columns:
        if 'Account ID' in df.columns and 'Reporting Date' in df.columns:
            df['UNIQUE REF'] = df['Account ID'].astype(str) + df['Reporting Date'].dt.strftime('%Y-%m-%d')
        else:
            raise KeyError("Required columns for UNIQUE REF creation are missing.")

    # Prepare a lookup dictionary for Performance classification by UNIQUE REF
    perf_lookup = {}
    if 'Performance classification' in df.columns and 'UNIQUE REF' in df.columns:
        perf_lookup = df.set_index('UNIQUE REF')['Performance classification'].to_dict()

    # Calculate PD Performance after qtr 1
    if 'PD Performance after qtr 1' not in df.columns:
        if 'UNIQUE REF' in df.columns and 'Reporting Date' in df.columns:
            def get_perf_after_qtr1(row):
                try:
                    key = row['Account ID'] + (row['Reporting Date'] + pd.offsets.MonthEnd(3)).strftime('%Y-%m-%d')
                    return perf_lookup.get(key, 'NA')
                except Exception:
                    return 'NA'
            df['PD Performance after qtr 1'] = df.apply(get_perf_after_qtr1, axis=1)
        else:
            df['PD Performance after qtr 1'] = 'NA'

    # Calculate PD Performance after qtr 2
    if 'PD Performance after qtr 2' not in df.columns:
        if 'UNIQUE REF' in df.columns and 'Reporting Date' in df.columns:
            def get_perf_after_qtr2(row):
                try:
                    key = row['Account ID'] + (row['Reporting Date'] + pd.offsets.MonthEnd(6)).strftime('%Y-%m-%d')
                    return perf_lookup.get(key, 'NA')
                except Exception:
                    return 'NA'
            df['PD Performance after qtr 2'] = df.apply(get_perf_after_qtr2, axis=1)
        else:
            df['PD Performance after qtr 2'] = 'NA'

    return df

def enrich_with_db_mappings(df, db: Session = None):
    """
    Enrich records with database-driven mappings.
    Assumes a mapping table for Account ID to additional fields like customer segment.
    """
    if db is None:
        db = SessionLocal()
    try:
        # Placeholder: Assume a CustomerMapping table
        # For now, add dummy enrichment
        if 'Account ID' in df.columns:
            # Example: Map Account ID to customer type
            df['Customer Type'] = df['Account ID'].apply(lambda x: 'Retail' if str(x).startswith('R') else 'Corporate')
            logging.info("Enriched records with DB mappings.")
        return df
    finally:
        db.close()

def merge_write_off_data(df, write_off_file_path='worktemplates/write_offs.xlsx'):
    """
    Merge write-off data before building PD performance states.
    """
    if not os.path.exists(write_off_file_path):
        logging.warning(f"Write-off file {write_off_file_path} not found. Skipping merge.")
        return df
    write_off_df = pd.read_excel(write_off_file_path)
    # Assume write_off_df has 'Account ID' and 'Write Off Amount'
    if 'Account ID' in df.columns and 'Account ID' in write_off_df.columns:
        df = df.merge(write_off_df, on='Account ID', how='left')
        df['Write Off Amount'] = df['Write Off Amount'].fillna(0)
        logging.info("Merged write-off data.")
    return df

def clean_inputs_with_helpers(df):
    """
    Clean inputs with shared helpers.
    """
    # Use shared helper: e.g., strip strings, handle NaNs
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    df = df.dropna(subset=['Account ID', 'Reporting Date'])
    logging.info("Cleaned inputs with shared helpers.")
    return df

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Adjust header_row if the actual header is not the first row (0-based)
    df = load_pd_input(header_row=1)
    print_columns(df)
    df = clean_inputs_with_helpers(df)
    df = enrich_with_db_mappings(df)
    df = merge_write_off_data(df)
    df = preprocess_pd_data(df)
    print("\nAfter preprocessing:")
    print_columns(df)
