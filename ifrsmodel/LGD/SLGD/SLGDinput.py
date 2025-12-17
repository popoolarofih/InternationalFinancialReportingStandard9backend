import pandas as pd
import numpy as np
import os
from datetime import datetime


from ...OtherInputs import load_other_inputs

def load_securedlgd_input(file_path='worktemplates/SecuredLGD.xlsx', header_row=1):
    """
    Load the Secured LGD input file and return the DataFrame.
    This function is designed to handle the user-uploaded file named SecuredLGD.xlsx.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found.")
    df = pd.read_excel(file_path, header=header_row)
    return df

def create_lgd_lookup_tables():
    """
    Load the data from OtherInputs.py for lookups, including repayment frequencies and collateral assumptions.
    Collateral assumptions include haircuts, time to recovery (TTR), and direct recovery costs per collateral type.
    """
    repayment_df, collateral_df = load_other_inputs()
    return repayment_df, collateral_df

# Helper: flexible column finder
def find_col(df, variants):
    """
    Finds a column in a DataFrame that matches one of the provided variants,
    handling case-insensitivity and partial matches.
    """
    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}
    for v in variants:
        if v is None:
            continue
        key = v.lower()
        if key in lower_map:
            return lower_map[key]
    for v in variants:
        if v is None:
            continue
        for c in cols:
            if v.lower() in c.lower():
                return c
    return None

def _parse_percentage(val):
    """
    Safely converts a value to a percentage (e.g., '20%' to 0.20 or 20 to 0.20).
    """
    if pd.isnull(val):
        return None
    if isinstance(val, (int, float)):
        if val > 1:
            return float(val) / 100.0
        return float(val)
    s = str(val).strip()
    if s.endswith('%'):
        try:
            return float(s.strip('%')) / 100.0
        except:
            return None
    try:
        f = float(s)
        if f > 1:
            return f / 100.0
        return f
    except:
        return None

def _safe_int(x):
    """Safely converts a value to an integer, returning None for non-numeric values."""
    try:
        if pd.isnull(x):
            return None
        return int(x)
    except:
        return None

def preprocess_secured_lgd(df, current_date=None, repayment_freq_lookup=None, collateral_lookup=None):
    """
    Preprocess Secured LGD input DataFrame to add computed columns based on the Secured LGD methodology.
    
    Methodology Overview:
    - Secured LGD considers collateral value (OMV), haircut, recovery time (TTR), discount rate (Effective Interest Rate), 
      and direct recovery costs.
    - Haircuts are applied to Open Market Value (OMV) provided by banks based on independent valuations, not forced sale values,
      to avoid punitive LGD calculations.
    - The collateral input includes OMV, haircuts, TTR, direct recovery costs, and Effective Rate (ER) for discounting.
    - Calculations:
      1. Adjusted Collateral = OMV * (1 - Haircut) * (1 - Direct Recovery Costs)
      2. Discounted Collateral = Adjusted Collateral / (1 + Effective Rate)^TTR
      3. Secured Recovery = min(1, Discounted Collateral / Outstanding Balance)
      4. Secured LGD = 1 - Secured Recovery
    - Uses supplied collateral data; falls back to lookups for missing values.
    """
    if current_date is None:
        current_date = pd.to_datetime(datetime.today()).normalize()
    else:
        current_date = pd.to_datetime(current_date).normalize()

    df = df.copy()

    # Column detection based on methodology inputs
    maturity_col = find_col(df, ['Loan Maturity Date'])
    disbursement_col = find_col(df, ['Loan Disbursement Date'])
    outstanding_col = find_col(df, ['Outstanding Balance (₦)'])
    collateral_val_col = find_col(df, ['Collateral Amount (OMV) (₦)'])  # OMV as per methodology
    haircut_col = find_col(df, ['Haircut'])
    interest_rate_col = find_col(df, ['Effective Interest rate (%)'])  # Discount rate (ER)
    collateral_desc_col = find_col(df, ['Collateral Description'])
    repayment_freq_text_col = find_col(df, ['Repayment Frequency'])
    ttr_col = find_col(df, ['TTR'])  # Time to Recovery
    direct_recovery_col = find_col(df, ['Direct Recovery'])  # Direct Recovery Costs
    account_id_col = find_col(df, ['Account ID'])

    # Tenor (Days) and Tenor (Months) - for reference, not directly used in LGD but part of input processing
    tenor_days_name = 'Tenor (Days)'
    tenor_months_name = 'Tenor (Months)'
    if maturity_col and disbursement_col:
        # Robust conversion: handle Excel serial numbers (numeric), already-datetime types, and strings
        def _convert_series_to_datetime(series):
            if pd.api.types.is_datetime64_any_dtype(series):
                return series
            if pd.api.types.is_numeric_dtype(series):
                # Excel serial date -> datetime
                return pd.to_timedelta(series, unit='D') + pd.Timestamp('1899-12-30')
            # fallback to parsing strings
            return pd.to_datetime(series, errors='coerce')

        df[disbursement_col] = _convert_series_to_datetime(df[disbursement_col])
        df[maturity_col] = _convert_series_to_datetime(df[maturity_col])

        # Compute tenor in days, floor negatives to 0
        td = (df[maturity_col] - df[disbursement_col]).dt.days
        df[tenor_days_name] = td.where(td >= 0, 0).fillna(0).astype(int)

        def calculate_datedif_months(row):
            start = row[disbursement_col]
            end = row[maturity_col]
            if pd.isnull(start) or pd.isnull(end):
                return None
            months = (end.year - start.year) * 12 + (end.month - start.month)
            if end.day < start.day:
                months -= 1
            return months

        df[tenor_months_name] = df.apply(calculate_datedif_months, axis=1)

    else:
        df[tenor_days_name] = None
        df[tenor_months_name] = None

    # Repayment Frequency in a Year (from lookups)
    if repayment_freq_lookup is not None and repayment_freq_text_col:
        freq_map = dict(zip(repayment_freq_lookup['Repayment Frequency'].str.lower(), repayment_freq_lookup['Times per Year']))
        df['Repayment Frequency in a Year'] = df[repayment_freq_text_col].str.lower().map(freq_map)

    # TTR, Haircut, Direct Recovery Costs - use provided values or lookup from collateral assumptions
    df['TTR'] = pd.to_numeric(df[ttr_col], errors='coerce') if ttr_col else None
    df['Haircut'] = df[haircut_col].apply(_parse_percentage) if haircut_col else None
    df['Direct Recovery'] = pd.to_numeric(df[direct_recovery_col], errors='coerce') if direct_recovery_col else None

    if collateral_lookup is not None and collateral_desc_col:
        coll_map_haircut = dict(zip(collateral_lookup['Collateral Description'], collateral_lookup['Haircut']))
        coll_map_ttr = dict(zip(collateral_lookup['Collateral Description'], collateral_lookup['Time to Recovery (years)']))
        coll_map_direct = dict(zip(collateral_lookup['Collateral Description'], collateral_lookup['Direct Recovery Cost']))

        if 'Haircut' in df.columns:
            df['Haircut'] = df.apply(lambda row: coll_map_haircut.get(row[collateral_desc_col], row['Haircut']) if pd.isnull(row['Haircut']) else row['Haircut'], axis=1)
        else:
            df['Haircut'] = df[collateral_desc_col].map(coll_map_haircut)
        
        if 'TTR' in df.columns:
            df['TTR'] = df.apply(lambda row: coll_map_ttr.get(row[collateral_desc_col], row['TTR']) if pd.isnull(row['TTR']) else row['TTR'], axis=1)
        else:
            df['TTR'] = df[collateral_desc_col].map(coll_map_ttr)
        
        if 'Direct Recovery' in df.columns:
            df['Direct Recovery'] = df.apply(lambda row: coll_map_direct.get(row[collateral_desc_col], row['Direct Recovery']) if pd.isnull(row['Direct Recovery']) else row['Direct Recovery'], axis=1)
        else:
            df['Direct Recovery'] = df[collateral_desc_col].map(coll_map_direct)

    # Fill any remaining NaNs with 0 as defaults
    df['Haircut'] = df['Haircut'].fillna(0)
    df['TTR'] = df['TTR'].fillna(0)
    df['Direct Recovery'] = df['Direct Recovery'].fillna(0)

    # Discounted Collateral calculation as per methodology
    discounted_name = 'Discounted Collateral'
    if collateral_val_col:
        df[collateral_val_col] = pd.to_numeric(df[collateral_val_col], errors='coerce').fillna(0)
        # Step 1: Apply haircut and direct recovery costs to OMV
        df[discounted_name] = df[collateral_val_col] * (1 - df['Haircut']) * (1 - df['Direct Recovery'])
        if interest_rate_col:
            # Parse discount rate (Effective Interest Rate)
            df['Effective Interest rate (%)'] = df[interest_rate_col].apply(_parse_percentage).fillna(0)
            # Step 2: Discount to present value using TTR
            df[discounted_name] /= (1 + df['Effective Interest rate (%)']) ** df['TTR']

    # Outstanding balance numeric
    if outstanding_col:
        df[outstanding_col] = pd.to_numeric(df[outstanding_col], errors='coerce').fillna(0)

    # Secured Recovery as per methodology
    def compute_secured_recovery(row):
        disc = row.get(discounted_name, 0)
        out_bal = row.get(outstanding_col, 0)
        if out_bal == 0:
            return 0
        # Step 3: min(1, Discounted / Outstanding)
        return min(1, disc / out_bal)

    df['Secured Recovery'] = df.apply(compute_secured_recovery, axis=1)

    # Secured LGD as per methodology
    # Step 4: 1 - Secured Recovery
    df['Secured LGD'] = 1 - df['Secured Recovery']
    
    return df

if __name__ == "__main__":
    df = load_securedlgd_input(header_row=1)
    print("Original Columns:")
    print(df.columns)
    
    # Load the lookup tables
    repayment_freq_df, collateral_df = create_lgd_lookup_tables()
    
    # Preprocess with current date (though not directly used in LGD calc)
    df_p = preprocess_secured_lgd(df, current_date='2025-09-09', repayment_freq_lookup=repayment_freq_df, collateral_lookup=collateral_df)
    
    print('\nAfter preprocessing, sample of new columns:')
    print(df_p[['Tenor (Days)', 'Tenor (Months)', 'Repayment Frequency in a Year', 'Discounted Collateral', 'Secured Recovery', 'Secured LGD']].head())