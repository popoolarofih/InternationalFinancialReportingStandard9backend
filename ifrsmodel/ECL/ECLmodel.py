import pandas as pd
import numpy as np
import os

class ECLModel:
    """
    Full rewrite of ECL model replicating Excel workbook logic exactly.
    """

    def __init__(self, base_path="worktemplates"):
        self.base_path = base_path
        self.raw_file = os.path.join(base_path, "Rawdata.xlsx")
        self.ead_file = os.path.join(base_path, "EAD_Term_Structure_Output.xlsx")
        self.df_file = os.path.join(base_path, "Discount_Factors.xlsx")
        self.pd_file = os.path.join(base_path, "PD_results_final.xlsx")
        self.lgd_file = os.path.join(base_path, "LGD_Final.xlsx")
        self.slgd_file = os.path.join(base_path, "SecuredLGD.xlsx")
        self.staging_file = os.path.join(base_path, "Staging.xlsx")
        self.output_file = os.path.join(base_path, "ECLFinalSummary_Rewrite.xlsx")

        self.scenario_weights = {
            "Base": 0.50,
            "Best": 0.25,
            "Worse": 0.25
        }
        # LGD sensible bounds
        self.LGD_MIN = 0.5
        self.LGD_MAX = 0.9
        self.LGD_FALLBACK = 0.53

    def load_excel(self, path, sheet_name=0, header=0):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        df = pd.read_excel(path, sheet_name=sheet_name, header=header)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    def load_all_data(self):
        self.raw_df = self.load_excel(self.raw_file, header=1)
        self.ead_df = self.load_excel(self.ead_file)
        self.df_df = self.load_excel(self.df_file)
        self.pd_dfs = self.load_pd_scenarios()
        self.lgd_df = self.load_lgd()
        self.slgd_df = self.load_slgd()
        self.staging_df = self.load_staging()

    def load_pd_scenarios(self):
        xls = pd.ExcelFile(self.pd_file)
        scenario_dfs = {}
        for scenario in self.scenario_weights.keys():
            # Try to find sheet matching scenario name (case insensitive)
            sheet_name = None
            for s in xls.sheet_names:
                if scenario.lower() in s.lower():
                    sheet_name = s
                    break
            if sheet_name:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                df.columns = [str(c).strip() for c in df.columns]
                scenario_dfs[scenario] = df
            else:
                scenario_dfs[scenario] = pd.DataFrame()
        return scenario_dfs

    def load_lgd(self):
        xls = pd.ExcelFile(self.lgd_file)
        sheet_name = xls.sheet_names[0]
        df = pd.read_excel(xls, sheet_name=sheet_name)
        df.columns = [str(c).strip() for c in df.columns]
        # Normalize LGD column and sector column
        sector_col = None
        lgd_col = None
        for c in df.columns:
            if "sector" in c.lower() or "segment" in c.lower():
                sector_col = c
            if "lgd" in c.lower():
                lgd_col = c
        if sector_col and lgd_col:
            df = df[[sector_col, lgd_col]].rename(columns={sector_col: "Business Sector", lgd_col: "LGD"})
            # Convert LGD to decimal if in percentage
            def safe_convert_lgd(x):
                try:
                    if isinstance(x, str):
                        if "%" in x:
                            return float(x.strip("%")) / 100
                        else:
                            return float(x)
                    elif pd.isna(x):
                        return 0.0
                    else:
                        return float(x)
                except:
                    return 0.0

            df["LGD"] = df["LGD"].apply(safe_convert_lgd)
        return df

    def load_slgd(self):
        from ..LGD.SLGD.SLGDinput import load_securedlgd_input, preprocess_secured_lgd, create_lgd_lookup_tables
        df = load_securedlgd_input(self.slgd_file, header_row=1)
        repayment_freq_df, collateral_df = create_lgd_lookup_tables()
        df = preprocess_secured_lgd(df, repayment_freq_lookup=repayment_freq_df, collateral_lookup=collateral_df)
        return df

    def load_staging(self):
        if os.path.exists(self.staging_file):
            df = pd.read_excel(self.staging_file)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        else:
            return pd.DataFrame()

    def get_pd(self, sector, scenario, period):
        df = self.pd_dfs.get(scenario)
        if df is None or df.empty:
            return 0.0
        sector_col = df.columns[0]
        # Match sector ignoring case and whitespace
        match = df[df[sector_col].str.strip().str.lower() == sector.strip().lower()]
        if match.empty:
            # Try contains
            match = df[df[sector_col].str.strip().str.lower().str.contains(sector.strip().lower())]
        if match.empty:
            return 0.0
        # Period columns are all columns except the sector column
        period_cols = [c for c in df.columns if c != sector_col]
        if period < len(period_cols):
            val = match.iloc[0][period_cols[period]]
            return float(val) if pd.notna(val) else 0.0
        return 0.0

    def get_lgd(self, sector):
        df = self.lgd_df
        if df.empty:
            return 0.0
        match = df[df["Business Sector"].str.strip().str.lower() == sector.strip().lower()]
        if match.empty:
            match = df[df["Business Sector"].str.strip().str.lower().str.contains(sector.strip().lower())]
        if match.empty:
            return 0.0
        try:
            lgd_val = float(match.iloc[0]["LGD"])
        except Exception:
            lgd_val = self.LGD_FALLBACK
        # clamp into [LGD_MIN, LGD_MAX]; if missing/zero use fallback then clamp
        if not (self.LGD_MIN <= lgd_val <= self.LGD_MAX):
            lgd_val = min(max(lgd_val if lgd_val else self.LGD_FALLBACK, self.LGD_MIN), self.LGD_MAX)
        return lgd_val

    def get_slgd(self, account_id):
        df = self.slgd_df
        if df.empty:
            return 0.0
        aid_col = None
        for c in df.columns:
            if "account" in c.lower() and "id" in c.lower():
                aid_col = c
                break
        if aid_col is None:
            return 0.0
        row = df[df[aid_col] == account_id]
        if row.empty:
            return 0.0
        try:
            slgd_val = float(row.iloc[0]["Secured LGD"])
        except Exception:
            return 0.0
        return slgd_val

    def get_ead(self, account_id, period):
        df = self.ead_df
        if df.empty:
            return 0.0
        aid_col = None
        for c in df.columns:
            if "account" in c.lower() and "id" in c.lower():
                aid_col = c
                break
        if aid_col is None:
            return 0.0
        row = df[df[aid_col] == account_id]
        if row.empty:
            return 0.0
        # Period columns assumed to be numeric or month names, take by index
        period_cols = [c for c in df.columns if c != aid_col]
        if period < len(period_cols):
            val = row.iloc[0][period_cols[period]]
            if pd.notna(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0
            else:
                return 0.0
        return 0.0

    def get_df(self, account_id, period):
        df = self.df_df
        if df.empty:
            return 1.0
        aid_col = None
        for c in df.columns:
            if "account" in c.lower() and "id" in c.lower():
                aid_col = c
                break
        if aid_col is None:
            return 1.0
        row = df[df[aid_col] == account_id]
        if row.empty:
            return 1.0
        period_cols = [c for c in df.columns if c != aid_col]
        if period < len(period_cols):
            val = row.iloc[0][period_cols[period]]
            if pd.notna(val):
                if isinstance(val, str) and "%" in val:
                    try:
                        return float(val.strip("%")) / 100
                    except (ValueError, TypeError):
                        return 1.0
                else:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 1.0
            else:
                return 1.0
        return 1.0

    def calculate_per_account_ecl(self, periods=13):
        results = []
        for idx, row in self.raw_df.iterrows():
            try:
                account_id = row.get("Account ID", "")
                account_name = row.get("Account Names", "")
                outstanding = row.get("Outstanding Balance (₦)", 0)
                if isinstance(outstanding, list):
                    outstanding = outstanding[0] if outstanding else 0
                outstanding = float(outstanding) if pd.notna(outstanding) else 0.0

                sector = ""
                for col in ["Business sector", "Business Sector"]:
                    if col in self.raw_df.columns:
                        sector = row.get(col, "")
                        break
                if isinstance(sector, list):
                    sector = sector[0] if sector else ""
                sector = str(sector).strip()
                stage = 1
                if "IFRS 9 STAGE" in self.raw_df.columns:
                    try:
                        stage = int(row.get("IFRS 9 STAGE", 1))
                    except:
                        stage = 1
                elif not self.staging_df.empty and "Account ID" in self.staging_df.columns:
                    # Find the FINAL STAGE column (it may have a date suffix)
                    final_stage_col = None
                    for col in self.staging_df.columns:
                        if "FINAL STAGE" in col.upper():
                            final_stage_col = col
                            break
                    if final_stage_col:
                        st_row = self.staging_df[self.staging_df["Account ID"] == account_id]
                        if not st_row.empty:
                            try:
                                stage = int(st_row[final_stage_col].iloc[0])
                            except:
                                stage = 1

                lgd_val = self.get_lgd(sector)
                slgd_val = self.get_slgd(account_id)

                ecl_periods = []
                pd_vals = []
                for p in range(periods):
                    ead = self.get_ead(account_id, p)
                    df = self.get_df(account_id, p)
                    weighted_pd_lgd = 0.0
                    for scenario, weight in self.scenario_weights.items():
                        pd_val = self.get_pd(sector, scenario, p)

                        # CORRECTION: Stage 3 accounts should have PD = 1.0
                        if int(stage) == 3:
                            pd_val = 1.0

                        pd_vals.append(pd_val)
                        weighted_pd_lgd += weight * (pd_val * lgd_val)
                    ecl_t = ead * df * weighted_pd_lgd
                    ecl_periods.append(float(ecl_t) if pd.notna(ecl_t) else 0.0)
                average_pd = sum(pd_vals) / len(pd_vals) if pd_vals else 0.0

                if stage == 1:
                    total_ecl = sum(ecl_periods[:12])
                elif stage == 2:
                    total_ecl = sum(ecl_periods)
                else:
                    # Stage 3: total_ecl = outstanding * slgd * lgd
                    total_ecl = outstanding * slgd_val * lgd_val

                # Handle matured loans
                maturity_checker = None
                for col in ["MATURITY CHECKER", "Maturity Checker"]:
                    if col in self.raw_df.columns:
                        maturity_checker = row.get(col)
                        break
                if isinstance(maturity_checker, list):
                    maturity_checker = maturity_checker[0] if maturity_checker else None
                if maturity_checker and str(maturity_checker).strip().upper() == "MATURED":
                    total_ecl = 0.0
                    ecl_periods = [0.0] * periods

                amount = row.get("Amount (₦)", 0)
                if isinstance(amount, list):
                    amount = amount[0] if amount else 0
                amount = float(amount) if pd.notna(amount) else 0.0

                effective = row.get("Effective Interest rate (%)", "")
                if isinstance(effective, list):
                    effective = effective[0] if effective else ""
                effective = str(effective).strip()

                disbursement = row.get("Loan Disbursement Date", "")
                if isinstance(disbursement, list):
                    disbursement = disbursement[0] if disbursement else ""
                disbursement = str(disbursement).strip()

                maturity_date = row.get("Loan Maturity Date", "")
                if isinstance(maturity_date, list):
                    maturity_date = maturity_date[0] if maturity_date else ""
                maturity_date = str(maturity_date).strip()

                results.append({
                    "S/n": idx + 1,
                    "Account ID": account_id,
                    "Account Names": account_name,
                    "Amount (₦)": amount,
                    "Outstanding Balance (₦)": outstanding,
                    "Effective Interest rate (%)": effective,
                    "Loan Disbursement Date": disbursement,
                    "Loan Maturity Date": maturity_date,
                    "Business Sector": sector,
                    "IFRS 9 STAGE": stage,
                    "Average PD": average_pd,
                    "LGD": lgd_val,
                    "Scenario Weighted ECL": total_ecl,
                    **{str(p): ecl_periods[p] for p in range(periods)}
                })
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                continue
        self.ecl_df = pd.DataFrame(results)

    def calculate_aggregations(self):
        # ECL by Segment
        seg_df = self.ecl_df.copy()
        seg_df["Stage"] = seg_df["IFRS 9 STAGE"].astype(str)
        seg_pivot = pd.pivot_table(
            seg_df,
            values=["Outstanding Balance (₦)", "Scenario Weighted ECL"],
            index=["Business Sector"],
            columns=["Stage"],
            aggfunc=np.sum,
            fill_value=0
        )
        seg_pivot.columns = ['_'.join(col).strip() for col in seg_pivot.columns.values]
        seg_pivot.reset_index(inplace=True)

        # Calculate total EAD and ECL by segment
        seg_pivot["EAD"] = seg_pivot[[col for col in seg_pivot.columns if col.startswith("Outstanding Balance")]].sum(axis=1)
        seg_pivot["Total ECL"] = seg_pivot[[col for col in seg_pivot.columns if col.startswith("Scenario Weighted ECL")]].sum(axis=1)

        # Calculate % to ECL
        total_ecl_sum = seg_pivot["Total ECL"].sum()
        seg_pivot["% to ECL"] = seg_pivot["Total ECL"] / total_ecl_sum

        self.ecl_by_segment = seg_pivot

        # ECL by Stage
        stage_df = self.ecl_df.copy()
        stage_group = stage_df.groupby("IFRS 9 STAGE").agg({
            "Outstanding Balance (₦)": "sum",
            "Scenario Weighted ECL": "sum"
        }).reset_index()
        stage_group.rename(columns={"Outstanding Balance (₦)": "EAD", "Scenario Weighted ECL": "ECL"}, inplace=True)
        total_ead = stage_group["EAD"].sum()
        total_ecl = stage_group["ECL"].sum()
        stage_group["%"] = stage_group["ECL"] / total_ecl

        self.ecl_by_stage = stage_group

    def export_to_excel(self):
        with pd.ExcelWriter(self.output_file, engine="xlsxwriter") as writer:
            self.ecl_df.to_excel(writer, sheet_name="ECL Summary", index=False)
            self.ecl_by_segment.to_excel(writer, sheet_name="ECL by Segment", index=False)
            self.ecl_by_stage.to_excel(writer, sheet_name="ECL by Stage", index=False)

            workbook = writer.book
            # Formatting
            money_fmt = workbook.add_format({"num_format": "#,##0.00"})
            percent_fmt = workbook.add_format({"num_format": "0.00%"})
            header_fmt = workbook.add_format({"bold": True, "bg_color": "#D7E4BC"})

            # Format ECL Summary sheet
            ws = writer.sheets["ECL Summary"]
            for col_num, value in enumerate(self.ecl_df.columns):
                width = 15 if col_num < 6 else 12
                ws.set_column(col_num, col_num, width, money_fmt if col_num >= 3 else None)
            ws.set_row(0, None, header_fmt)

            # Format ECL by Segment sheet
            ws = writer.sheets["ECL by Segment"]
            for col_num, value in enumerate(self.ecl_by_segment.columns):
                width = 20 if col_num == 0 else 15
                fmt = money_fmt if value not in ["Business Sector", "% to ECL"] else percent_fmt if value == "% to ECL" else None
                ws.set_column(col_num, col_num, width, fmt)
            ws.set_row(0, None, header_fmt)

            # Format ECL by Stage sheet
            ws = writer.sheets["ECL by Stage"]
            for col_num, value in enumerate(self.ecl_by_stage.columns):
                width = 15 if col_num != 0 else 10
                fmt = money_fmt if value in ["EAD", "ECL"] else percent_fmt if value == "%" else None
                ws.set_column(col_num, col_num, width, fmt)
            ws.set_row(0, None, header_fmt)

    def run(self):
        self.load_all_data()
        self.calculate_per_account_ecl()
        self.calculate_aggregations()
        self.export_to_excel()
        print(f"ECL summary and aggregations exported to {self.output_file}")


def main():
    model = ECLModel()
    model.run()


if __name__ == "__main__":
    main()
