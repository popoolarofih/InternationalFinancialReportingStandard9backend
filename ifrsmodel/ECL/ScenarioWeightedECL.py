# ScenarioWeightedECL.py
import pandas as pd
import numpy as np
import os
import warnings
from typing import Dict, Any


def to_excel_serial(date):
    """Convert pandas Timestamp to Excel serial date."""
    if isinstance(date, pd.Timestamp):
        return (date - pd.Timestamp('1899-12-30')).days
    return date

warnings.filterwarnings("ignore")

# Scenario weights 
SCENARIO_WEIGHTS = {
    "Base": 0.50,
    "Best": 0.25,    # sometimes called "Best" or "Upside"
    "Worse": 0.25    # sometimes called "Worse" or "Downside"
}

# add small LGD range defaults near top of file (after SCENARIO_WEIGHTS)
LGD_MIN = 0.5
LGD_MAX = 0.9
LGD_FALLBACK = 0.53


# -------------------------
# Helpers / Loaders
# -------------------------
def safe_read_excel(path: str, sheet_name: Any = 0, header: int = 0) -> pd.DataFrame:
    """Read excel with friendly error messaging."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    return pd.read_excel(path, sheet_name=sheet_name, header=header)


def load_raw_data(path: str) -> pd.DataFrame:
    df = safe_read_excel(path, header=1)
    # Normalize column names (strip whitespace/newlines)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    print(f"✅ Loaded raw data: {df.shape}")
    return df


def load_ead_term_structure(path: str) -> pd.DataFrame:
    try:
        df = safe_read_excel(path, sheet_name="EAD_Term_Structure")
    except Exception:
        # try first sheet
        df = safe_read_excel(path, sheet_name=0)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    print(f"✅ Loaded EAD term structure: {df.shape}")
    return df


def load_discount_factors(path: str) -> pd.DataFrame:
    try:
        df = safe_read_excel(path, sheet_name="Discount_Factors")
    except Exception:
        df = safe_read_excel(path, sheet_name=0)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    print(f"✅ Loaded discount factors: {df.shape}")
    return df


def load_pd_results(path: str) -> Dict[str, pd.DataFrame]:
    """
    Attempt to load PD results for the three scenarios.
    Flexible with sheet names: tries several common variants.
    Returns dict: {'Base': df, 'Best': df, 'Worse': df}
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"PD file not found: {path}")

    xls = pd.ExcelFile(path)
    sheets = [s.lower() for s in xls.sheet_names]
    mapping = {}

    # candidate names for each scenario
    candidates = {
        "Base": ["base", "base_marginal", "base marginal pds", "base marginal", "scenario weighted", "scenario_weighted"],
        "Best": ["best", "best_marginal", "best marginal pds", "upside", "best_marginal_pds"],
        "Worse": ["worse", "worse_marginal", "worse marginal pds", "downside"]
    }

    for key, names in candidates.items():
        found = None
        for n in names:
            if n.lower() in sheets:
                # exact match (case-insensitive)
                # get original sheet name
                idx = sheets.index(n.lower())
                found = xls.sheet_names[idx]
                break
        if not found:
            # try partial matches
            for s in xls.sheet_names:
                if any(n in s.lower() for n in names):
                    found = s
                    break
        if found:
            df = pd.read_excel(xls, sheet_name=found, header=0)
            df.columns = [str(c).strip() for c in df.columns]
            mapping[key] = df
        else:
            # No sheet found for this scenario: create empty df
            mapping[key] = pd.DataFrame()
    print(f"✅ Loaded PD results: Base={mapping['Base'].shape}, Best={mapping['Best'].shape}, Worse={mapping['Worse'].shape}")
    return mapping


def load_lgd_results(path: str) -> pd.DataFrame:
    """
    Load LGD final table. Try common sheet names, then fallback to first sheet.
    Normalize to columns: 'Business Sector' and 'LGD'
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"LGD file not found: {path}")

    xls = pd.ExcelFile(path)
    # try likely names
    candidates = ["final lgd", "final lgd table", "lgd", "lgd_final", "lgd results"]
    found = None
    for name in xls.sheet_names:
        if any(c in name.lower() for c in candidates):
            found = name
            break
    if not found:
        found = xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=found, header=0)
    df.columns = [str(c).strip() for c in df.columns]

    # attempt to find sector and lgd columns
    col_map = {c.lower(): c for c in df.columns}
    sector_col = col_map.get("segment") or col_map.get("business sector") or col_map.get("sector")
    lgd_col = None
    for candidate in ["unsecured lgd", "unsecured_lgd", "lgd", "unsecuredlgd", "unsecured lgd"]:
        if candidate in col_map:
            lgd_col = col_map[candidate]
            break
    # fallback to any numeric last column
    if sector_col is None:
        raise KeyError(f"Could not find business sector column in LGD sheet (columns: {df.columns.tolist()})")
    if lgd_col is None:
        # pick last numeric column
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        lgd_col = numeric_cols[-1] if numeric_cols else None
    if lgd_col is None:
        raise KeyError(f"Could not find LGD numeric column in LGD sheet (columns: {df.columns.tolist()})")

    df = df[[sector_col, lgd_col]].rename(columns={sector_col: "Business Sector", lgd_col: "LGD"})
    # convert percentages where applicable
    df["LGD"] = df["LGD"].apply(lambda x: (float(str(x).strip("%")) / 100.0) if isinstance(x, str) and "%" in str(x) else (float(x) if pd.notna(x) else 0.0))
    print(f"✅ Loaded LGD data: {df.shape}")
    return df


def load_staging_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_excel(path, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"✅ Loaded staging data: {df.shape}")
    return df


# -------------------------
# Lookup helpers
# -------------------------
def get_pd_value_for_sector(pd_mapping: Dict[str, pd.DataFrame], sector: str, scenario_key: str, period: int) -> float:
    """
    Period is 0-based here; PD tables normally use 1..12 columns -> we'll map period->period+1
    If sector not found or pd cell missing, return 0.0
    """
    df = pd_mapping.get(scenario_key)
    if df is None or df.empty:
        return 0.0

    # try to locate sector column/row
    # assume first column is sector name
    first_col = df.columns[0]
    tmp = df.copy()
    tmp[first_col] = tmp[first_col].astype(str).str.strip()
    match = tmp[tmp[first_col].str.lower() == str(sector).lower()]
    if match.empty:
        # try fuzzy match: startswith or contains
        mask = tmp[first_col].str.lower().str.contains(str(sector).lower())
        match = tmp[mask]
    if match.empty:
        return 0.0

    # period columns are commonly '1','2',... or integers
    period_col_candidates = [str(period + 1), period + 1]
    found_col = None
    for c in tmp.columns:
        if str(c).strip() in period_col_candidates:
            found_col = c
            break
    if found_col is None:
        # try numeric columns (first numeric)
        num_cols = [c for c in tmp.columns if pd.api.types.is_numeric_dtype(tmp[c])]
        if num_cols:
            # map to position relative to first numeric column
            # choose numeric column index = period (if exists)
            if period < len(num_cols):
                found_col = num_cols[period]
            else:
                return 0.0
        else:
            # maybe columns are labeled like '1','2',.. as strings; check them
            for c in tmp.columns:
                if str(c).strip().isdigit():
                    if int(str(c).strip()) == (period + 1):
                        found_col = c
                        break
    if found_col is None:
        return 0.0

    val = match.iloc[0][found_col]
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except Exception:
        # maybe percent string
        if isinstance(val, str) and "%" in val:
            return float(val.strip("%")) / 100.0
        return 0.0


def get_lgd_for_sector(lgd_df: pd.DataFrame, sector: str) -> float:
    if lgd_df is None or lgd_df.empty:
        return 0.0
    mask = lgd_df["Business Sector"].astype(str).str.strip().str.lower() == str(sector).lower()
    row = lgd_df.loc[mask]
    if row.empty:
        # try contains
        mask = lgd_df["Business Sector"].astype(str).str.strip().str.lower().str.contains(str(sector).lower())
        row = lgd_df.loc[mask]
        if row.empty:
            return 0.0
    val = row["LGD"].iloc[0]
    try:
        return float(val)
    except Exception:
        return 0.0


def get_ead_for_account(ead_df: pd.DataFrame, account_id: str, period: int) -> float:
    if ead_df is None or ead_df.empty:
        return 0.0
    if "Account ID" not in ead_df.columns:
        # try common variants
        candidates = [c for c in ead_df.columns if "account" in c.lower() and "id" in c.lower()]
        if candidates:
            aid_col = candidates[0]
        else:
            return 0.0
    else:
        aid_col = "Account ID"
    account_row = ead_df[ead_df[aid_col] == account_id]
    if account_row.empty:
        return 0.0

    # find monthly projection columns (months names)
    period_cols = [c for c in ead_df.columns if any(m in str(c) for m in ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"])]
    if period < len(period_cols):
        val = account_row[period_cols[period]].iloc[0]
        return float(0 if pd.isna(val) else val)
    return 0.0


def get_df_for_account(df_df: pd.DataFrame, account_id: str, period: int) -> float:
    if df_df is None or df_df.empty:
        return 1.0
    if "Account ID" not in df_df.columns:
        candidates = [c for c in df_df.columns if "account" in c.lower() and "id" in c.lower()]
        if candidates:
            aid_col = candidates[0]
        else:
            return 1.0
    else:
        aid_col = "Account ID"
    account_row = df_df[df_df[aid_col] == account_id]
    if account_row.empty:
        return 1.0
    period_cols = [c for c in df_df.columns if any(m in str(c) for m in ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"])]
    if period < len(period_cols):
        val = account_row[period_cols[period]].iloc[0]
        if isinstance(val, str) and "%" in val:
            try:
                return float(val.strip("%")) / 100.0
            except:
                return 1.0
        try:
            return float(val)
        except:
            return 1.0
    return 1.0


# -------------------------
# Main ECL calculation
# -------------------------
def calculate_scenario_weighted_ecl(raw_df: pd.DataFrame,
                                    ead_df: pd.DataFrame,
                                    df_df: pd.DataFrame,
                                    pd_mapping: Dict[str, pd.DataFrame],
                                    lgd_df: pd.DataFrame,
                                    staging_df: pd.DataFrame,
                                    periods: int = 14) -> pd.DataFrame:
    """
    periods = 14 means period 0..13 (0 = reporting date)
    """

    current_serial = 45937  # Excel serial for 2025-10-07

    # desired output columns
    columns = ["S/n", "Account ID", "Account Names", "Amount (₦)", "Outstanding Balance (₦)",
               "Effective Interest rate (%)", "Loan Disbursement Date", "Loan Maturity Date",
               "Business Sector", "IFRS 9 STAGE", "ECL"] + [str(i) for i in range(periods)]

    out_rows = []

    for idx, row in raw_df.iterrows():
        account_id = row.get("Account ID", "")
        account_name = row.get("Account Names", "")
        amount = row.get("Amount (₦)", 0)
        outstanding = row.get("Outstanding Balance (₦)", 0)

        # business sector (some raw files use 'Business sector' or 'Business Sector')
        sector = None
        for cands in ["Business sector", "Business Sector", "business sector"]:
            if cands in raw_df.columns:
                sector = row.get(cands, "")
                break
        if sector is None:
            sector = ""

        # IFRS 9 stage: prefer raw file column "IFRS 9 STAGE"
        if "IFRS 9 STAGE" in raw_df.columns:
            stage = row.get("IFRS 9 STAGE", 1)
            # ensure numeric
            try:
                stage = int(stage)
            except:
                stage = 1
        else:
            # fallback to staging file (if provided)
            stage = 1
            if not staging_df.empty and "Account ID" in staging_df.columns:
                st_row = staging_df[staging_df["Account ID"] == account_id]
                if not st_row.empty and "FINAL STAGE" in st_row.columns:
                    stage = st_row["FINAL STAGE"].iloc[0]
                    try:
                        stage = int(stage)
                    except:
                        stage = 1

        # obtain LGD for sector and clamp into sensible range
        lgd_val = get_lgd_for_sector(lgd_df, sector)
        try:
            lgd_val = float(lgd_val)
        except Exception:
            lgd_val = LGD_FALLBACK
        # enforce LGD between LGD_MIN and LGD_MAX (use fallback if out of range)
        if not (LGD_MIN <= lgd_val <= LGD_MAX):
            lgd_val = min(max(lgd_val if lgd_val else LGD_FALLBACK, LGD_MIN), LGD_MAX)

        # compute per-period ECLs
        ecl_periods = []
        for p in range(periods):
            ead_t = get_ead_for_account(ead_df, account_id, p)
            df_t = get_df_for_account(df_df, account_id, p)

            # scenario-weighted PD * LGD
            weighted_pd_lgd = 0.0
            for scenario_key, weight in SCENARIO_WEIGHTS.items():
                # note: mapping keys we loaded earlier are 'Base','Best','Worse' etc.
                # try to map our internal name to the expected loader names:
                pd_sheet_key = None
                # Accept synonyms
                if scenario_key.lower() in ["base", "base case", "base_marginal", "scenario weighted"]:
                    pd_sheet_key = "Base"
                elif scenario_key.lower() in ["best", "upside"]:
                    pd_sheet_key = "Best"
                elif scenario_key.lower() in ["worse", "downside"]:
                    pd_sheet_key = "Worse"
                else:
                    pd_sheet_key = scenario_key

                pd_val = get_pd_value_for_sector(pd_mapping, sector, pd_sheet_key, p)

                # CORRECTION: If this account is already Stage 3 (default), PD should be 1.0
                if int(stage) == 3:
                    pd_val = 1.0

                weighted_pd_lgd += weight * (pd_val * lgd_val)

            ecl_t = ead_t * df_t * weighted_pd_lgd
            if pd.isna(ecl_t) or np.isinf(ecl_t):
                ecl_t = 0.0
            ecl_periods.append(float(ecl_t))

        # total ECL by stage rules
        if stage == 1:
            total_ecl = sum(ecl_periods[:12])  # 12-month ECL
        elif stage == 2:
            total_ecl = sum(ecl_periods)      # lifetime ECL
        else:  # stage 3
            total_ecl = ecl_periods[0] if ecl_periods else 0.0

        # matured loans handling based on maturity date
        maturity_date = row.get("Loan Maturity Date", float('inf'))
        maturity_date = to_excel_serial(maturity_date)
        if maturity_date <= current_serial:
            total_ecl = 0.0
            ecl_periods = [0.0] * periods

        out = {
            "S/n": idx + 1,
            "Account ID": account_id,
            "Account Names": account_name,
            "Amount (₦)": amount,
            "Outstanding Balance (₦)": outstanding,
            "Effective Interest rate (%)": row.get("Effective Interest rate (%)", ""),
            "Loan Disbursement Date": row.get("Loan Disbursement Date", ""),
            "Loan Maturity Date": row.get("Loan Maturity Date", ""),
            "Business Sector": sector,
            "IFRS 9 STAGE": stage,
            "ECL": float(total_ecl)
        }
        # fill period values
        for p in range(periods):
            out[str(p)] = ecl_periods[p]
        out_rows.append(out)

    result_df = pd.DataFrame(out_rows, columns=columns)
    return result_df


def add_portfolio_totals(result_df: pd.DataFrame, periods: int = 14) -> pd.DataFrame:
    totals = {
        "S/n": "",
        "Account ID": "PORTFOLIO TOTAL",
        "Account Names": "",
        "Amount (₦)": result_df["Amount (₦)"].sum(),
        "Outstanding Balance (₦)": result_df["Outstanding Balance (₦)"].sum(),
        "Effective Interest rate (%)": "",
        "Loan Disbursement Date": "",
        "Loan Maturity Date": "",
        "Business Sector": "",
        "IFRS 9 STAGE": "",
        "ECL": result_df["ECL"].sum()
    }
    for p in range(periods):
        totals[str(p)] = result_df[str(p)].sum()
    # prepend
    result = pd.concat([pd.DataFrame([totals]), result_df], ignore_index=True)
    return result


def export_to_excel(result_df: pd.DataFrame, out_path: str):
    period_dates = [45838, 45869, 45900, 45930, 45961, 45991, 46022, 46053, 46081, 46112, 46142, 46173, 46203, 46234]
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        result_df.to_excel(writer, sheet_name="Scenario_Weighted_ECL", index=False, startrow=1)
        workbook = writer.book
        worksheet = writer.sheets["Scenario_Weighted_ECL"]
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#F0F0F0", "border": 1})
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        number_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        # write period dates in row 0, starting from column 11
        worksheet.write_row(0, 11, period_dates)
        # set widths + formats
        for i, col in enumerate(result_df.columns):
            w = 18 if i > 2 else 20
            worksheet.set_column(i, i, w, number_fmt)
            worksheet.write(1, i, col, header_fmt)
    print(f"📂 Exported results to {out_path}")


# -------------------------
# Run as script
# -------------------------
def main():
    print("🚀 Starting Scenario-Weighted ECL Calculation...")

    base_path = os.path.join("worktemplates")
    raw_file = os.path.join(base_path, "Rawdata.xlsx")
    ead_file = os.path.join(base_path, "EAD_Term_Structure_Output.xlsx")
    df_file = os.path.join(base_path, "Discount_Factors.xlsx")
    pd_file = os.path.join(base_path, "PD_results_final.xlsx")   # produced by your PD pipeline
    lgd_file = os.path.join(base_path, "LGD_Final.xlsx")        # produced by your LGD pipeline
    staging_file = os.path.join(base_path, "Staging.xlsx")
    output_file = os.path.join(base_path, "Scenario_Weighted_ECL_Output.xlsx")

    raw_df = load_raw_data(raw_file)
    ead_df = load_ead_term_structure(ead_file)
    df_df = load_discount_factors(df_file)
    pd_mapping = load_pd_results(pd_file)
    lgd_df = load_lgd_results(lgd_file)
    staging_df = load_staging_data(staging_file)

    result_df = calculate_scenario_weighted_ecl(raw_df, ead_df, df_df, pd_mapping, lgd_df, staging_df, periods=14)
    result_df = add_portfolio_totals(result_df, periods=14)
    export_to_excel(result_df, output_file)

    print("✅ Scenario-Weighted ECL calculation completed successfully!")


if __name__ == "__main__":
    main()
