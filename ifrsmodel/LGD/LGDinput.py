# ifrsmodel/LGD/LGDmodel.py
import pandas as pd
import numpy as np
import os

LGD_FALLBACK = 0.53  # Default LGD if calculation fails or is missing

import logging
logger = logging.getLogger(__name__)


def load_lgd_input(file_path='worktemplates/LGD.xlsx', header_row=1):
    """Load the LGD input file and return the DataFrame."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found.")
    df = pd.read_excel(file_path, header=header_row)
    return df


def print_columns(df):
    """Print all columns in the DataFrame."""
    print("Columns in the LGD input file:")
    for col in df.columns:
        print(col)


def preprocess_lgd_data(df):
    """Preprocess LGD data (dates, references, repayment logic)."""
    df['Reporting Date'] = pd.to_datetime(df['Reporting Date'], errors='coerce')
    df['UNIQUE REF'] = df['Account ID'].astype(str) + df['Reporting Date'].dt.strftime('%d-%b-%y')

    def eomonth(date, months):
        if pd.isnull(date):
            return pd.NaT
        month = date.month - 1 + months
        year = date.year + month // 12
        month = month % 12 + 1
        return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)

    df['EOMONTH_3'] = df['Reporting Date'].apply(lambda x: eomonth(x, 3))
    df['EOMONTH_6'] = df['Reporting Date'].apply(lambda x: eomonth(x, 6))

    df['REF_3'] = df['Account ID'].astype(str) + df['EOMONTH_3'].dt.strftime('%d-%b-%y')
    df['REF_6'] = df['Account ID'].astype(str) + df['EOMONTH_6'].dt.strftime('%d-%b-%y')

    # Use the clean, standardized column that exists in your data
    perf_col = 'Performance Classification 2' if 'Performance Classification 2' in df.columns else 'Performance classification'
    ref_to_perf = dict(zip(df['UNIQUE REF'], df[perf_col]))
    ref_to_bal = dict(zip(df['UNIQUE REF'], df['Outstanding Balance (₦)']))

    df['LGD Performance after one quarter'] = df['REF_3'].map(ref_to_perf).fillna('NA')
    df['Repayment Amount after one quarter'] = df['REF_3'].map(ref_to_bal).fillna(0)
    df['LGD Performance after two quarters'] = df['REF_6'].map(ref_to_perf).fillna('NA')

    df['Written Off'] = df.get('Written Off', 0)

    def calc_repayment_amount(row):
        try:
            perf_class = row['Performance classification']
            lgd_perf_qtr = row['LGD Performance after one quarter']
            out_bal = row['Outstanding Balance (₦)']
            repay_amt_qtr = row['Repayment Amount after one quarter']
            written_off = row['Written Off'] if pd.notnull(row['Written Off']) else 0
            if perf_class == "Default" and (lgd_perf_qtr in ["Default", "NA"]):
                return max(0, out_bal - repay_amt_qtr - written_off)
            else:
                return 0
        except Exception:
            return 0

    df['Repayment Amount'] = df.apply(calc_repayment_amount, axis=1)

    df.drop(['EOMONTH_3', 'EOMONTH_6', 'REF_3', 'REF_6'], axis=1, inplace=True)
    return df


def compute_lgd_migration_table(df, sectors, statuses, quarters):
    """Compute LGD Migration table for each business sector and status across quarters."""
    migration_rows = []
    for sector in sectors:
        for status in statuses:
            quarter_sums = []
            for i, q in enumerate(quarters):
                mask = (
                    (df['Business sector'] == sector) &
                    (df['Performance Classification 2'] == status) &
                    (df['Reporting Date'] == q)
                )
                quarter_sum = df.loc[mask, 'Outstanding Balance (₦)'].sum()
                quarter_sums.append(quarter_sum)
            total_migrations = sum(quarter_sums)
            # Dynamic column names based on quarters
            row = {
                'Sector': sector,
                'Performing Status': status,
                'Total Migrations': total_migrations,
            }
            for i, q in enumerate(quarters):
                row[f'Q{i+1}'] = quarter_sums[i]  # Use Q1, Q2, etc.
            migration_rows.append(row)
    return pd.DataFrame(migration_rows)


def compute_quarterly_sums(df, sectors):
    """Compute quarterly cure/recovery rates properly per quarter (not pooled)"""
    results = []
    df['Outstanding Balance (₦)'] = pd.to_numeric(df['Outstanding Balance (₦)'], errors='coerce').fillna(0)
    df['Repayment Amount'] = pd.to_numeric(df['Repayment Amount'], errors='coerce').fillna(0)

    for sector in sectors:
        sector_df = df[df['Business sector'] == sector].copy()

        # Defaulted exposure at t=0 (Reporting Date)
        defaulted_exposure = sector_df[
            sector_df['Performance Classification 2'] == 'Default'
        ]['Outstanding Balance (₦)'].sum()

        # Cured = defaults that became Performing after 1 quarter
        cured = sector_df[
            (sector_df['Performance Classification 2'] == 'Default') &
            (sector_df['LGD Performance after one quarter'] == 'Performing')
        ]['Outstanding Balance (₦)'].sum()

        # Recovered = repayment amount from defaulted accounts (even if still Default)
        recovered = sector_df[
            sector_df['Performance Classification 2'] == 'Default'
        ]['Repayment Amount'].sum()

        # Stayed in Default
        stayed_default = defaulted_exposure - cured - recovered

        total = cured + recovered + stayed_default

        results.append({
            'SEGMENT': sector,
            'Sum of Defaults': defaulted_exposure,
            'CURED ACCOUNTS': cured,
            'RECOVERIES': recovered,
            'DEFAULT': stayed_default,
            'TOTAL': total,
            'Redefaults': 0  # You currently have no redefault data
        })

    return pd.DataFrame(results)


def compute_average_migration_matrix(quarterly_sums_df):
    """Compute Average Migration Matrix for each sector (3 rows)."""
    all_results = []
    for _, row in quarterly_sums_df.iterrows():
        sector = row['SEGMENT']
        cured = row['CURED ACCOUNTS'] if row['CURED ACCOUNTS'] != '-' else 0
        recoveries = row['RECOVERIES'] if row['RECOVERIES'] != '-' else 0
        defaulted = row['DEFAULT'] if row['DEFAULT'] != '-' else 0
        total = row['TOTAL'] if row['TOTAL'] != '-' else 0
        redefaults = row['Redefaults'] if row['Redefaults'] != '-' else 0

        cure_rate = (cured / total) if total else 0
        recovery_rate = (recoveries / total) if total else 0
        default_rate = (defaulted / total) if total else 0
        redefault_rate = (redefaults / defaulted) if defaulted else 0

        all_results.append({
            'SEGMENT': sector, 'ACCOUNT TYPE': 'CURED ACCOUNTS',
            'CURE RATE': 1.0, 'RECOVERY RATE': 0.0,
            'DEFAULT RATE': 0.0, 'REDEFAULT RATE': 0.0
        })
        all_results.append({
            'SEGMENT': sector, 'ACCOUNT TYPE': 'RECOVERIES',
            'CURE RATE': 0.0, 'RECOVERY RATE': 1.0,
            'DEFAULT RATE': 0.0, 'REDEFAULT RATE': 0.0
        })
        all_results.append({
            'SEGMENT': sector, 'ACCOUNT TYPE': 'DEFAULTED ACCOUNTS',
            'CURE RATE': cure_rate, 'RECOVERY RATE': recovery_rate,
            'DEFAULT RATE': default_rate, 'REDEFAULT RATE': redefault_rate
        })

    return pd.DataFrame(all_results)


def compute_mmult_quarters(avg_migration_df, quarters=4):
    """Compute MMULT quarterly transition matrices for each sector."""
    results = []
    for sector in avg_migration_df['SEGMENT'].unique():
        row = avg_migration_df[
            (avg_migration_df['SEGMENT'] == sector) &
            (avg_migration_df['ACCOUNT TYPE'] == 'DEFAULTED ACCOUNTS')
        ].iloc[0]

        cure_rate, recovery_rate, default_rate = row['CURE RATE'], row['RECOVERY RATE'], row['DEFAULT RATE']

        transition_matrix = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [cure_rate, recovery_rate, default_rate]
        ])

        cured, recovered, defaulted = np.array([1,0,0]), np.array([0,1,0]), np.array([0,0,1])

        for q in range(1, quarters+1):
            cured_next = np.matmul(cured, np.linalg.matrix_power(transition_matrix, q))
            recovered_next = np.matmul(recovered, np.linalg.matrix_power(transition_matrix, q))
            defaulted_next = np.matmul(defaulted, np.linalg.matrix_power(transition_matrix, q))

            results.extend([
                {"SEGMENT": sector, "QUARTER": q, "ACCOUNT TYPE": "CURED ACCOUNTS",
                 "CURE RATE": cured_next[0], "RECOVERY RATE": cured_next[1], "DEFAULT RATE": cured_next[2]},
                {"SEGMENT": sector, "QUARTER": q, "ACCOUNT TYPE": "RECOVERIES",
                 "CURE RATE": recovered_next[0], "RECOVERY RATE": recovered_next[1], "DEFAULT RATE": recovered_next[2]},
                {"SEGMENT": sector, "QUARTER": q, "ACCOUNT TYPE": "DEFAULTED ACCOUNTS",
                 "CURE RATE": defaulted_next[0], "RECOVERY RATE": defaulted_next[1], "DEFAULT RATE": defaulted_next[2]},
            ])
    return pd.DataFrame(results)


def compute_final_lgd(mmult_results, avg_migration_df, lgd_fallback=LGD_FALLBACK):
    """Compute Final LGD Table per sector with configurable fallback."""
    final_rows = []
    for sector in mmult_results['SEGMENT'].unique():
        q4_matrix = mmult_results[
            (mmult_results['SEGMENT'] == sector) &
            (mmult_results['QUARTER'] == 4) &
            (mmult_results['ACCOUNT TYPE'] == 'DEFAULTED ACCOUNTS')
        ].iloc[0]

        cure_rate, recovery_rate, default_rate = q4_matrix['CURE RATE'], q4_matrix['RECOVERY RATE'], q4_matrix['DEFAULT RATE']

        redefault_row = avg_migration_df[
            (avg_migration_df['SEGMENT'] == sector) &
            (avg_migration_df['ACCOUNT TYPE'] == 'DEFAULTED ACCOUNTS')
        ].iloc[0]
        redefault_rate = redefault_row['REDEFAULT RATE']

        # CORRECT IFRS 9 LGD FORMULA (exactly as in your Excel sheet)
        # LGD = 1 – (Cumulative Cure Rate at horizon × (1 – Redefault Rate))
        # Recovery Rate is already reflected in the repayment logic, so we don't double-count
        net_cure_contribution = cure_rate * (1.0 - redefault_rate)
        unsecured_lgd = 1.0 - net_cure_contribution

        # Only apply 53% fallback when calculation completely fails (e.g. division by zero)
        # Do NOT apply fallback just because LGD is low!
        if pd.isna(unsecured_lgd) or unsecured_lgd < 0 or unsecured_lgd > 1:
            unsecured_lgd = LGD_FALLBACK  # 0.53
        else:
            # Optional: apply conservative floor if required by your regulator/policy
            unsecured_lgd = max(unsecured_lgd, 0.10)  # e.g. minimum 10% LGD

        final_rows.append({
            "SEGMENT": sector,
            "CURE RATE": cure_rate,
            "RECOVERY RATE": recovery_rate,
            "REDEFAULT RATE": redefault_rate,
            "UNSECURED LGD": unsecured_lgd
        })

    return pd.DataFrame(final_rows)


if __name__ == "__main__":
    df = load_lgd_input(header_row=1)
    print_columns(df)
    df = preprocess_lgd_data(df)

    sectors = df['Business sector'].dropna().unique()
    statuses = ['Performing', 'Default', 'Watchlist']
    quarters = sorted(df['Reporting Date'].dropna().unique())  # Dynamic quarters from data

    migration_df = compute_lgd_migration_table(df, sectors, statuses, quarters)
    print("\nMigration Table:")
    print(migration_df)

    quarterly_sums_df = compute_quarterly_sums(df, sectors)
    print("\nQuarterly Sums Table:")
    print(quarterly_sums_df)

    avg_migration_df = compute_average_migration_matrix(quarterly_sums_df)
    mmult_results = compute_mmult_quarters(avg_migration_df, quarters=4)
    final_lgd_df = compute_final_lgd(mmult_results, avg_migration_df)

    print("\nFinal LGD Table (with fallback 53% if missing):")
    print(final_lgd_df)

    # -------------------------
    # Save all results to Excel
    # -------------------------
    out_path = os.path.join("worktemplates", "LGD_Final.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Preprocessed Data", index=False)
        migration_df.to_excel(writer, sheet_name="Migration Table", index=False)
        quarterly_sums_df.to_excel(writer, sheet_name="Quarterly Sums", index=False)
        avg_migration_df.to_excel(writer, sheet_name="Avg Migration Matrix", index=False)
        mmult_results.to_excel(writer, sheet_name="MMULT Results", index=False)
        final_lgd_df.to_excel(writer, sheet_name="Final LGD Table", index=False)

    print(f"\n📂 LGD results saved to {out_path}")
