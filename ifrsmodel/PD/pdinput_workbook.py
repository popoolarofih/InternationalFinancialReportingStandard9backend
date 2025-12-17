import os
import pandas as pd


def load_pd_input(file_path='worktemplates/pd_input.xlsx', header_row=1):
    """
    Load the PD input file and return the DataFrame.
    header_row: zero-based index of the row containing the column headers
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
    Preprocess the PD input DataFrame to align with workbook logic:
    - Convert date columns to datetime (timezone-naive)
    - Create UNIQUE REF = str(Account ID) + Reporting Date (YYYY-MM-DD)
    - Build next-state lookup from Performance classification 2
    - Compute PD Performance after qtr 1 and qtr 2 via keyed lookups
    - Normalize key string columns to avoid whitespace/case mismatches
    """
    df = df.copy()

    # 1) Convert date columns to datetime
    date_cols = ['Loan Disbursement Date', 'Loan Maturity Date', 'Reporting Date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 2) Normalize key categorical columns used by downstream logic
    if 'Performance classification 2' in df.columns:
        df['Performance classification 2'] = (
            df['Performance classification 2']
            .astype(str)
            .str.strip()
            .str.title()
        )
    if 'Business sector' in df.columns:
        df['Business sector'] = df['Business sector'].astype(str).str.strip()

    # 3) UNIQUE REF used for lookups, consistent string formatting
    if 'UNIQUE REF' not in df.columns:
        if 'Account ID' in df.columns and 'Reporting Date' in df.columns:
            df['UNIQUE REF'] = df['Account ID'].astype(str) + df['Reporting Date'].dt.strftime('%Y-%m-%d')
        else:
            raise KeyError("Required columns for UNIQUE REF creation are missing.")

    # 4) Build lookup from UNIQUE REF -> Performance classification 2 (the workbook's next-state basis)
    perf2_lookup = {}
    if 'Performance classification 2' in df.columns and 'UNIQUE REF' in df.columns:
        perf2_lookup = df.set_index('UNIQUE REF')['Performance classification 2'].to_dict()

    # 5) Compute PD Performance after qtr 1 via exact key alignment
    if 'PD Performance after qtr 1' not in df.columns:
        def next_state_q1(row):
            acc = row.get('Account ID')
            rep = row.get('Reporting Date')
            if pd.isna(acc) or pd.isna(rep):
                return 'NA'
            key = str(acc) + (pd.to_datetime(rep) + pd.offsets.MonthEnd(3)).strftime('%Y-%m-%d')
            return perf2_lookup.get(key, 'NA')

        df['PD Performance after qtr 1'] = df.apply(next_state_q1, axis=1)

    # 6) Compute PD Performance after qtr 2 via exact key alignment
    if 'PD Performance after qtr 2' not in df.columns:
        def next_state_q2(row):
            acc = row.get('Account ID')
            rep = row.get('Reporting Date')
            if pd.isna(acc) or pd.isna(rep):
                return 'NA'
            key = str(acc) + (pd.to_datetime(rep) + pd.offsets.MonthEnd(6)).strftime('%Y-%m-%d')
            return perf2_lookup.get(key, 'NA')

        df['PD Performance after qtr 2'] = df.apply(next_state_q2, axis=1)

    return df


if __name__ == "__main__":
    # Demo when running this module directly
    df = load_pd_input(header_row=1)
    print_columns(df)
    df = preprocess_pd_data(df)
    print("\nAfter preprocessing (workbook-aligned):")
    print_columns(df)

