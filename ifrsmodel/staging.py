import pandas as pd
from .PD import pdinput

def find_col(df, variants):
    # Case-insensitive exact match or substring match
    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}
    for v in variants:
        if v.lower() in lower_map:
            return lower_map[v.lower()]
    for v in variants:
        for c in cols:
            if v.lower() in c.lower():
                return c
    return None

def map_performance_class(perf):
    # If already numeric (1/2/3), return as int
    try:
        if pd.isnull(perf):
            return None
        if isinstance(perf, (int, float)):
            return int(perf)
        perf_str = str(perf).strip()
        if perf_str.isdigit():
            return int(perf_str)
        perf_str = perf_str.lower()
        if perf_str == 'performing':
            return 1
        if perf_str == 'watchlist':
            return 2
        # Excel formula default branch treats any other value as stage 3
        return 3
    except Exception:
        pass
    return None


def map_dpd(dpd):
    # If already stage 1/2/3 return it; if actual days, convert to stage
    try:
        if pd.isnull(dpd):
            return None
        if isinstance(dpd, (int, float)):
            val = int(dpd)
            if val in (1, 2, 3):
                return val
            # value appears to be days past due
            if val <= 30:
                return 1
            if val <= 89:
                return 2
            return 3
        dpd_str = str(dpd).strip()
        if dpd_str.isdigit():
            return map_dpd(int(dpd_str))
    except Exception:
        pass
    return None


def create_staging_table(pd_df):
    output = pd.DataFrame()
    # 1. S/n
    output['S/n'] = range(1, len(pd_df) + 1)
    output['Account ID'] = pd_df.get('Account ID')
    output['Account Names'] = pd_df.get('Account Names')
    output['Outstanding Balance (₦)'] = pd_df.get('Outstanding Balance (₦)')

    # Detect Q1 columns
    perf_q1_col = find_col(pd_df, ['PERFORMANCE CLASS', 'Performance classification', 'Performance Class', 'PERF', 'P'])
    dpd_q1_col = find_col(pd_df, ['DPD', 'Days past Due', 'Days past Due (DPD)', 'Days past Due (DPD)'])
    final_q1_col = find_col(pd_df, ['FINAL QTR STAGE', 'FINAL QTR STAGE (31-Mar-25)', 'FINAL_QTR_STAGE'])

    # PERF CLASS Q1
    if perf_q1_col:
        output['PERFORMANCE CLASS (31-Mar-25)'] = pd_df[perf_q1_col].apply(map_performance_class)
    else:
        output['PERFORMANCE CLASS (31-Mar-25)'] = None
    # DPD Q1
    if dpd_q1_col:
        output['DPD (31-Mar-25)'] = pd_df[dpd_q1_col].apply(map_dpd)
    else:
        output['DPD (31-Mar-25)'] = None
    # FINAL Q1: prefer existing if present
    if final_q1_col:
        output['FINAL QTR STAGE (31-Mar-25)'] = pd_df[final_q1_col].apply(lambda x: int(x) if pd.notnull(x) else None)
    else:
        output['FINAL QTR STAGE (31-Mar-25)'] = output[['PERFORMANCE CLASS (31-Mar-25)', 'DPD (31-Mar-25)']].max(axis=1)

    # Detect Q2 columns
    # include explicit PD input names used in the workbook (e.g. "Performance classification 2" and "Days past Due (DPD)")
    perf_q2_col = find_col(pd_df, ['Performance classification 2', 'PD Performance after qtr 1', 'PERFORMANCE CLASS (30-Jun-25)', 'PERFORMANCE CLASS Q2'])
    dpd_q2_col = find_col(pd_df, ['Days past Due (DPD)', 'Days Past Due after qtr 1', 'DPD after qtr 1', 'DPD (Q2)', 'DPD_1', 'DPD (30-Jun-25)'])
    final_q2_col = find_col(pd_df, ['FINAL QTR STAGE (30-Jun-25)', 'FINAL QTR STAGE Q2', 'FINAL_QTR_STAGE_2'])

    # PERFORMANCE CLASS Q2: prefer explicit PD column; fallback to FINAL Q2 (if present),
    # else reuse Q1 performance class, else derive from Q2 DPD if available.
    if perf_q2_col:
        output['PERFORMANCE CLASS (30-Jun-25)'] = pd_df[perf_q2_col].apply(map_performance_class)
    else:
        if final_q2_col:
            # if a final q2 stage exists in the PD input, use it as performance class
            output['PERFORMANCE CLASS (30-Jun-25)'] = pd_df[final_q2_col].apply(lambda x: int(x) if pd.notnull(x) else None)
        elif 'PERFORMANCE CLASS (31-Mar-25)' in output.columns:
            # fall back to prior quarter performance class
            output['PERFORMANCE CLASS (30-Jun-25)'] = output['PERFORMANCE CLASS (31-Mar-25)']
        elif dpd_q2_col:
            # as a last resort, derive performance class from dpd (days past due -> stage)
            output['PERFORMANCE CLASS (30-Jun-25)'] = pd_df[dpd_q2_col].apply(map_dpd)
        else:
            output['PERFORMANCE CLASS (30-Jun-25)'] = None

    if dpd_q2_col:
        output['DPD (30-Jun-25)'] = pd_df[dpd_q2_col].apply(map_dpd)
    else:
        output['DPD (30-Jun-25)'] = None
    # FINAL Q2: prefer existing if present
    if final_q2_col:
        output['FINAL QTR STAGE (30-Jun-25)'] = pd_df[final_q2_col].apply(lambda x: int(x) if pd.notnull(x) else None)
    else:
        output['FINAL QTR STAGE (30-Jun-25)'] = output[['PERFORMANCE CLASS (30-Jun-25)', 'DPD (30-Jun-25)']].max(axis=1)

    # PROBATIONARY STAGING: prefer existing column
    if find_col(pd_df, ['PROBATIONARY STAGING', 'L1']):
        col = find_col(pd_df, ['PROBATIONARY STAGING', 'L1'])
        output['PROBATIONARY STAGING'] = pd_df[col].apply(lambda x: int(x) if pd.notnull(x) else None)
    else:
        output['PROBATIONARY STAGING'] = output['FINAL QTR STAGE (31-Mar-25)'].apply(lambda x: max(0, int(x)-1) if pd.notnull(x) else None)

    # FINAL STAGE: prefer existing column
    if find_col(pd_df, ['FINAL STAGE', 'M1']):
        col = find_col(pd_df, ['FINAL STAGE', 'M1'])
        output['FINAL STAGE'] = pd_df[col].apply(lambda x: int(x) if pd.notnull(x) else None)
    else:
        # FINAL STAGE = MAX(FINAL QTR STAGE (30-Jun-25), PROBATIONARY STAGING)
        output['FINAL STAGE'] = output[['FINAL QTR STAGE (30-Jun-25)', 'PROBATIONARY STAGING']].max(axis=1)

    # Reorder columns to match expected staging sheet
    output = output[['S/n', 'Account ID', 'Account Names', 'Outstanding Balance (₦)',
                     'PERFORMANCE CLASS (31-Mar-25)', 'DPD (31-Mar-25)', 'FINAL QTR STAGE (31-Mar-25)',
                     'PERFORMANCE CLASS (30-Jun-25)', 'DPD (30-Jun-25)', 'FINAL QTR STAGE (30-Jun-25)',
                     'PROBATIONARY STAGING', 'FINAL STAGE']]
    return output

if __name__ == "__main__":
    df = pdinput.load_pd_input(header_row=1)
    df = pdinput.preprocess_pd_data(df)
    staging_table = create_staging_table(df)
    print(staging_table.head())