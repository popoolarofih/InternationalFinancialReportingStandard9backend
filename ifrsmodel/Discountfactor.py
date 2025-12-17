import pandas as pd
import numpy as np
from pandas.tseries.offsets import MonthEnd
import os


def calculate_discount_factors(df, reporting_date="2025-06-30", months=12):
    df = df.copy()

    # Convert Effective Interest Rate (%) from raw input
    df["Effective Interest rate (%)"] = pd.to_numeric(
        df["Effective Interest rate (%)"], errors="coerce"
    ).fillna(0)

    # Create clean decimal version for calculations
    df["Effective Rate Clean"] = np.where(
        df["Effective Interest rate (%)"] > 1,
        df["Effective Interest rate (%)"] / 100,
        df["Effective Interest rate (%)"],
    )

    # Monthly EIR
    df["Monthly EIR"] = (1 + df["Effective Rate Clean"]) ** (1 / 12) - 1

    # Projection dates (end of month)
    reporting_date = pd.to_datetime(reporting_date)
    projection_dates = pd.date_range(
        reporting_date, reporting_date + MonthEnd(months), freq="ME"
    )

    # Compute Discount Factors
    for t, proj_date in enumerate(projection_dates):
        col_name = proj_date.strftime("%d-%b-%y")
        df[col_name] = 1 / (1 + df["Monthly EIR"]) ** t
        df[col_name] = (df[col_name] * 100).round(1).astype(str) + "%"  # format as %

    # Keep only needed columns for output
    keep_cols = ["S/n", "Account ID", "Account Names", "Effective Interest rate (%)"] + [
        d.strftime("%d-%b-%y") for d in projection_dates
    ]
    df = df[keep_cols]

    # Format Effective Interest Rate (%) for display
    df["Effective Interest rate (%)"] = (
        df["Effective Interest rate (%)"].round(2).astype(str) + "%"
    )

    return df


if __name__ == "__main__":
    raw_df = pd.read_excel("worktemplates/Rawdata.xlsx", header=1)

    # Clean headers
    raw_df.columns = [str(c).replace("\n", " ").strip() for c in raw_df.columns]

    print("✅ Loaded data:", raw_df.shape)

    discount_df = calculate_discount_factors(raw_df)

    # Save to Excel
    out_path = os.path.join("worktemplates", "Discount_Factors.xlsx")
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        discount_df.to_excel(writer, sheet_name="Discount_Factors", index=False)

        # Format sheet
        workbook = writer.book
        worksheet = writer.sheets["Discount_Factors"]
        worksheet.set_column(0, len(discount_df.columns) - 1, 15)

    print(f"📂 Saved discount factors to: {out_path}")
