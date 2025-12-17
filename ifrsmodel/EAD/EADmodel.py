# ifrsmodel/EAD/EADmodel.py
import pandas as pd
import numpy as np
from pandas.tseries.offsets import MonthEnd
import os

# ----------------------------
# Utility functions
# ----------------------------
def _clean_rate(rate):
    """Return rate in decimal form. Handles 16.87 (percent) or 0.1687 (decimal)."""
    try:
        r = float(rate)
    except Exception:
        return 0.0
    return r / 100.0 if r > 1 else r


def _pmt(payment_rate, n_periods, pv):
    """
    Equivalent of Excel PMT.
    r = periodic rate, n = number periods, pv = present value (positive)
    returns periodic payment (positive)
    """
    r = payment_rate
    n = int(n_periods)
    if n <= 0 or r <= 0 or pv == 0:
        return 0.0
    try:
        return pv * r * (1 + r) ** n / ((1 + r) ** n - 1)
    except Exception:
        return 0.0


# ----------------------------
# Core function
# ----------------------------
def calculate_ead_term_structure(
    df: pd.DataFrame,
    months_forward: int = 13,
    add_adj_maturity_days: int = 7,
):
    """
    Enrich raw loan DataFrame with EAD term structure columns and projections.

    Parameters
    ----------
    df : pd.DataFrame
        Raw input DataFrame with expected columns.
    months_forward : int
        Number of months to project (default = 13).
    add_adj_maturity_days : int
        Days added to maturity to build ADJ Maturity Date.

    Returns
    -------
    pd.DataFrame
        Enriched DataFrame with derived columns and projection columns.
    """

    df = df.copy()

    # Required cleaning and type conversions
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    df["Reporting Date"] = pd.to_datetime(df["Reporting Date"], errors="coerce")
    df["Loan Disbursement Date"] = pd.to_datetime(df["Loan Disbursement Date"], errors="coerce")
    df["Loan Maturity Date"] = pd.to_datetime(df["Loan Maturity Date"], errors="coerce")

    # ADJ Maturity Date
    df["ADJ Maturity Date"] = df["Loan Maturity Date"] + pd.Timedelta(days=add_adj_maturity_days)

    # Tenor (Months)
    if "Tenor (Months)" in df.columns:
        df["Tenor (Months)"] = pd.to_numeric(df["Tenor (Months)"], errors="coerce").fillna(0).astype(int)
    else:
        df["Tenor (Months)"] = (pd.to_numeric(df.get("Tenor (Days)", 0), errors="coerce") / 30.417).round().astype(int)

    # Tenor To Maturity (Months)
    df["Tenor To Maturity (Months)"] = np.maximum(0, ((df["ADJ Maturity Date"] - df["Reporting Date"]).dt.days / 30.417).round().astype(int))

    # MATURITY CHECKER
    df["MATURITY CHECKER"] = np.where(df["ADJ Maturity Date"] > df["Reporting Date"], "NOT MATURED", "MATURED")

    # Numeric cleanups
    df["Outstanding Balance (₦)"] = pd.to_numeric(df["Outstanding Balance (₦)"], errors="coerce").fillna(0.0)
    df["Credit/Sanction Limit (₦)"] = pd.to_numeric(df.get("Credit/Sanction Limit (₦)", 0), errors="coerce").fillna(0.0)

    # Undrawn Overdraft: IF(AND(Type="Overdraft", Credit>Outstanding), Credit-Outstanding, 0)
    df["Undrawn Overdraft"] = np.where(
        (df["Types of facilities"].astype(str).str.upper() == "OVERDRAFT")
        & (df["Credit/Sanction Limit (₦)"] > df["Outstanding Balance (₦)"]),
        df["Credit/Sanction Limit (₦)"] - df["Outstanding Balance (₦)"],
        0.0,
    )

    # Effective Rate clean
    df["Effective Rate Clean"] = df["Effective Interest rate (%)"].apply(_clean_rate)

    # PERIODIC EIR = (1+rate)^(1/12)-1
    df["PERIODIC EIR"] = (1 + df["Effective Rate Clean"]).pow(1.0 / 12.0) - 1.0

    # TERM IN FORCE
    df["TERM IN FORCE"] = ((df["Reporting Date"] - df["Loan Disbursement Date"]).dt.days / 30.417).astype(int).fillna(0).astype(int)

    # REPAYMENT PATTERN
    df["Repayment Frequency in a Year"] = pd.to_numeric(df["Repayment Frequency in a Year"], errors="coerce").fillna(0)
    df["REPAYMENT PATTERN"] = np.where(df["Repayment Frequency in a Year"] > 0, 12 / df["Repayment Frequency in a Year"], np.nan)

    # NUMBER OF PAYMENTS PER MONTH
    df["NUMBER OF PAYMENTS PER MONTH"] = np.where(
        (df["REPAYMENT PATTERN"] > 0) & (df["Tenor (Months)"] >= 0),
        np.floor(df["Tenor (Months)"] / df["REPAYMENT PATTERN"]).astype(int),
        0,
    )

    # OUTSTANDING BALANCE INCLUDING UNDRAWN FOR ODs
    # Fixed CCF = 20% for overdrafts
    def compute_outstanding_including_undrawn(row):
        if str(row["Types of facilities"]).upper() == "OVERDRAFT":
            undrawn = float(row["Undrawn Overdraft"])
            return row["Outstanding Balance (₦)"] + 0.20 * undrawn
        else:
            return row["Outstanding Balance (₦)"]

    df["OUTSTANDING BALANCE INCLUDING UNDRAWN FOR ODs"] = df.apply(compute_outstanding_including_undrawn, axis=1)

    # PMT
    def calc_pmt(row):
        outstanding = row["Outstanding Balance (₦)"]
        r = row["PERIODIC EIR"]
        n = int(row["Tenor To Maturity (Months)"]) if not pd.isna(row["Tenor To Maturity (Months)"]) else 0
        types_ = str(row.get("Types of facilities", "")).upper()
        matured = str(row.get("MATURITY CHECKER", "")).upper() == "MATURED"

        if matured:
            return outstanding
        if types_ in ("OVERDRAFT", "BULLET"):
            return 0.0
        if n <= 0 or r <= 0 or outstanding <= 0:
            return 0.0

        return _pmt(r, n, outstanding)

    df["PMT"] = df.apply(calc_pmt, axis=1)

    # ----------------------------
    # Projection / monthly EAD generation
    # ----------------------------
    start_date = df["Reporting Date"].min()
    projection_dates = pd.date_range(start_date, start_date + MonthEnd(months_forward), freq="M")

    projection_cols = []
    for idx, proj_date in enumerate(projection_dates, start=1):
        col_name = proj_date.strftime("%d-%b-%y")
        projection_cols.append(col_name)

    projections = {col: [] for col in projection_cols}
    for _, row in df.iterrows():
        periodic_r = float(row["PERIODIC EIR"])
        start_bal = float(row["OUTSTANDING BALANCE INCLUDING UNDRAWN FOR ODs"])
        pmta = float(row["PMT"])
        adjm = row["ADJ Maturity Date"]
        term_in_force = int(row.get("TERM IN FORCE", 0))
        try:
            repayment_interval = int(round(row["REPAYMENT PATTERN"]))
            if repayment_interval <= 0:
                repayment_interval = None
        except Exception:
            repayment_interval = None

        loan_type = str(row.get("Types of facilities", "")).upper()
        matured_flag = str(row.get("MATURITY CHECKER", "")).upper() == "MATURED"

        prev_bal = start_bal
        for period_idx, proj_date in enumerate(projection_dates, start=1):
            if pd.isnull(adjm) or proj_date > adjm:
                projections[proj_date.strftime("%d-%b-%y")].append(0.0)
                prev_bal = 0.0
                continue

            if prev_bal <= 0:
                projections[proj_date.strftime("%d-%b-%y")].append(0.0)
                prev_bal = 0.0
                continue

            bal_after_interest = prev_bal * (1 + periodic_r)

            payment_due = 0.0
            if repayment_interval is not None and repayment_interval > 0 and loan_type not in ("OVERDRAFT", "BULLET"):
                if ((term_in_force + period_idx) % repayment_interval) == 0:
                    payment_due = pmta

            if loan_type == "BULLET":
                if proj_date >= adjm:
                    payment_due = bal_after_interest
                    bal_after_interest = 0.0

            next_bal = max(0.0, bal_after_interest - payment_due)

            if proj_date >= adjm:
                next_bal = 0.0

            projections[proj_date.strftime("%d-%b-%y")].append(next_bal)
            prev_bal = next_bal

    for col in projection_cols:
        df[col] = projections[col]

    # Round numeric outputs
    numeric_cols = [
        "Outstanding Balance (₦)",
        "Credit/Sanction Limit (₦)",
        "Undrawn Overdraft",
        "OUTSTANDING BALANCE INCLUDING UNDRAWN FOR ODs",
        "PERIODIC EIR",
        "PMT",
        "TERM IN FORCE",
        "NUMBER OF PAYMENTS PER MONTH",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

# ----------------------------
# Script entry point
# ----------------------------
if __name__ == "__main__":
    IN_PATH = os.path.join("worktemplates", "Rawdata.xlsx")
    OUT_PATH = os.path.join("worktemplates", "EAD_Term_Structure_Output.xlsx")

    if not os.path.exists(IN_PATH):
        raise FileNotFoundError(f"Input file not found: {IN_PATH}")

    raw_df = pd.read_excel(IN_PATH, header=1)
    print("Loaded data:", raw_df.shape)
    print("Columns:", raw_df.columns.tolist())

    enriched = calculate_ead_term_structure(raw_df, months_forward=13)

    with pd.ExcelWriter(OUT_PATH, engine="xlsxwriter") as writer:
        enriched["Reporting Date"] = pd.to_datetime(enriched["Reporting Date"], errors="coerce").dt.strftime("%d-%b-%y")
        enriched["Loan Disbursement Date"] = pd.to_datetime(enriched["Loan Disbursement Date"], errors="coerce").dt.strftime("%d-%b-%y")

        enriched.to_excel(writer, sheet_name="EAD_Term_Structure", index=False)
        workbook = writer.book
        worksheet = writer.sheets["EAD_Term_Structure"]

        money_fmt = workbook.add_format({"num_format": "#,##0.00"})
        percent_fmt = workbook.add_format({"num_format": "0.00%"})
        date_fmt = workbook.add_format({"num_format": "dd-mmm-yy"})

        for col_idx, col_name in enumerate(enriched.columns):
            if "Balance" in col_name or "Overdraft" in col_name or col_name == "PMT":
                worksheet.set_column(col_idx, col_idx, 16, money_fmt)
            elif "EIR" in col_name:
                worksheet.set_column(col_idx, col_idx, 12, percent_fmt)
            elif "Date" in col_name or "Maturity" in col_name:
                worksheet.set_column(col_idx, col_idx, 12, date_fmt)
            else:
                worksheet.set_column(col_idx, col_idx, 14)

    print(f"📂 Saved enriched EAD term structure to: {OUT_PATH}")
