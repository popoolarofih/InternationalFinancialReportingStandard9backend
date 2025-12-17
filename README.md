# IFRS 9 Model Logics Detailed

This document provides a comprehensive, step-by-step explanation of the logics used to calculate each component of the IFRS 9 models: Probability of Default (PD), Loss Given Default (LGD), Exposure at Default (EAD), Expected Credit Loss (ECL), and Staging. The calculations are based on the Python implementations in the codebase, replicating Excel workbook logics.

## 1. Probability of Default (PD) Model

The PD model calculates the probability of default for each business sector across quarterly periods. It uses migration data from historical performance classifications.

### Data Loading and Preprocessing (pdinput.py)

1. **Load PD Input File**:
   - File: `worktemplates/pd_input.xlsx`
   - Header row: Row 1 (0-based index)
   - Columns include: Account ID, Reporting Date, Business sector, Outstanding Balance (₦), Performance classification, etc.

2. **Preprocess PD Data**:
   - Clean 'Business sector' column: Strip whitespace, remove empty entries
   - Convert date columns to datetime: Loan Disbursement Date, Loan Maturity Date, Reporting Date
   - Create UNIQUE REF column: `Account ID + Reporting Date (YYYY-MM-DD)`
   - Calculate PD Performance after qtr 1: Lookup performance classification 3 months ahead using UNIQUE REF
   - Calculate PD Performance after qtr 2: Lookup performance classification 6 months ahead using UNIQUE REF

3. **Enrich with DB Mappings**:
   - Add Customer Type based on Account ID prefix (e.g., 'R' for Retail, else Corporate)

4. **Merge Write-off Data**:
   - Merge from `worktemplates/write_offs.xlsx` on Account ID
   - Add Write Off Amount column (default 0 if not found)

5. **Clean Inputs**:
   - Strip string values, drop rows with missing Account ID or Reporting Date

### PD Migration Calculation (PDmodel.py)

1. **calculate_pd_migration Function**:
   - **Inputs**: Preprocessed PD DataFrame, segments list, performing statuses, reporting dates, optional FLI scalars
   - **Logic**:
     - For each segment (Business sector):
       - For each performing status (Performing, Default):
         - Initialize row with SEGMENT and PERFORMING STATUS
         - For each reporting date:
           - Filter data: Business sector == segment, Performance classification 2 == status, Reporting Date matches, PD Performance after qtr 1 != 'NA' and not null
           - Sum Outstanding Balance (₦) for filtered rows
           - Apply FLI scalar if available: sum_val *= FLI scalar for that period
           - Store in row[reporting_date_str]
         - Calculate TOTAL MIGRATIONS: Sum of all quarterly sums
     - **Output Columns**: SEGMENT, PERFORMING STATUS, TOTAL MIGRATIONS, [reporting_date_str columns]

2. **generate_quarterly_dates Function**:
   - Generate list of quarterly end dates starting from start_date
   - Uses pd.offsets.QuarterEnd

3. **Main Function**:
   - Load and preprocess PD data
   - Get dynamic segments from data
   - Set performing statuses: ['Performing', 'Default']
   - Generate reporting dates (default 4 quarters from 2024-09-30, or from provided reporting_date)
   - Load FLI model scalars from `worktemplates\Updated FLI Scenario Weights Inputs - 31.03.25 20250530.xlsx`
   - Calculate migration table
   - Print results

### PD Output
- Migration table with rows per segment/status, columns for total migrations and quarterly sums
- FLI scalars applied to quarterly sums if available

## 2. Loss Given Default (LGD) Model

The LGD model calculates the loss rate given default for each business sector, using historical recovery data over quarters.

### Data Loading and Preprocessing (LGDinput.py)

1. **Load LGD Input File**:
   - File: `worktemplates/LGD.xlsx`
   - Header row: Row 1
   - Columns include: Account ID, Reporting Date, Business sector, Outstanding Balance (₦), Performance Classification 2, etc.

2. **Preprocess LGD Data**:
   - Convert Reporting Date to datetime
   - Create UNIQUE REF: `Account ID + Reporting Date (dd-Mon-yy)`
   - Calculate EOMONTH_3: End of month 3 months after Reporting Date
   - Calculate EOMONTH_6: End of month 6 months after Reporting Date
   - Create REF_3: `Account ID + EOMONTH_3 (dd-Mon-yy)`
   - Create REF_6: `Account ID + EOMONTH_6 (dd-Mon-yy)`
   - Lookup LGD Performance after one quarter: Map REF_3 to Performance classification 2
   - Lookup Repayment Amount after one quarter: Map REF_3 to Outstanding Balance (₦)
   - Lookup LGD Performance after two quarters: Map REF_6 to Performance classification 2
   - Calculate Repayment Amount:
     - If Performance classification == "Default" and LGD Performance after one quarter in ["Default", "NA"]:
       - Repayment Amount = max(0, Outstanding Balance - Repayment Amount after one quarter - Written Off)
     - Else: 0
   - Drop temporary columns: EOMONTH_3, EOMONTH_6, REF_3, REF_6

### LGD Migration and Calculations

1. **compute_lgd_migration_table Function**:
   - **Inputs**: Preprocessed df, sectors, statuses, quarters
   - **Logic**:
     - For each sector:
       - For each status (Performing, Default, Watchlist):
         - For each quarter:
           - Filter: Business sector == sector, Performance Classification 2 == status, Reporting Date == quarter
           - Sum Outstanding Balance (₦)
         - Store quarterly sums
         - Total Migrations = sum of quarterly sums
     - **Output Columns**: Sector, Performing Status, Total Migrations, Q3 2024, Q4 2024, Q1 2025, Q2 2025

2. **compute_quarterly_sums Function**:
   - **Inputs**: df, sectors
   - **Logic**:
     - For each sector:
       - Sum of Defaults: Sum Outstanding Balance where sector matches, status == 'Default', LGD Performance after one quarter == 'Performing'
       - Cured Accounts: Sum Repayment Amount where sector matches, LGD Performance after one quarter == 'Default'
       - Recoveries: Sum Outstanding Balance where sector matches, status == 'Default', LGD Performance after one quarter == 'Default'
       - DEFAULT: Sum of Defaults + Recoveries
       - TOTAL: Sum of Sum of Defaults, Cured Accounts, Recoveries, DEFAULT
       - Redefaults: Sum Outstanding Balance where sector matches, status == 'Default', LGD Performance after one quarter == 'Performing', LGD Performance after two quarters == 'Default'
     - **Output Columns**: SEGMENT, Sum of Defaults, CURED ACCOUNTS, RECOVERIES, DEFAULT, TOTAL, Redefaults

3. **compute_average_migration_matrix Function**:
   - **Inputs**: quarterly_sums_df
   - **Logic**:
     - For each sector:
       - Cure Rate = CURED ACCOUNTS / TOTAL (if TOTAL > 0)
       - Recovery Rate = RECOVERIES / TOTAL
       - Default Rate = DEFAULT / TOTAL
       - Redefault Rate = Redefaults / DEFAULT (if DEFAULT > 0)
     - **Output Rows**:
       - CURED ACCOUNTS: CURE RATE=1.0, RECOVERY RATE=0.0, DEFAULT RATE=0.0, REDEFAULT RATE=0.0
       - RECOVERIES: CURE RATE=0.0, RECOVERY RATE=1.0, DEFAULT RATE=0.0, REDEFAULT RATE=0.0
       - DEFAULTED ACCOUNTS: CURE RATE=cure_rate, RECOVERY RATE=recovery_rate, DEFAULT RATE=default_rate, REDEFAULT RATE=redefault_rate

4. **compute_mmult_quarters Function**:
   - **Inputs**: avg_migration_df, quarters=4
   - **Logic**:
     - For each sector:
       - Get cure_rate, recovery_rate, default_rate from DEFAULTED ACCOUNTS row
       - Create transition matrix:
         ```
         [[1.0, 0.0, 0.0],
          [0.0, 1.0, 0.0],
          [cure_rate, recovery_rate, default_rate]]
         ```
       - For each quarter (1 to 4):
         - Cured next = matrix_power(transition_matrix, q) @ [1,0,0]
         - Recovered next = matrix_power(transition_matrix, q) @ [0,1,0]
         - Defaulted next = matrix_power(transition_matrix, q) @ [0,0,1]
         - Store rates for each account type
     - **Output Columns**: SEGMENT, QUARTER, ACCOUNT TYPE, CURE RATE, RECOVERY RATE, DEFAULT RATE

5. **compute_final_lgd Function**:
   - **Inputs**: mmult_results, avg_migration_df
   - **Logic**:
     - For each sector:
       - Get Q4 rates for DEFAULTED ACCOUNTS
       - Unsecured LGD = (1 - cure_rate) * (1 - redefault_rate)
       - If LGD missing or <=0, use fallback 53%
     - **Output Columns**: SEGMENT, CURE RATE, RECOVERY RATE, REDEFAULT RATE, UNSECURED LGD

### LGD Output
- Final LGD table per sector with unsecured LGD (fallback 53% if invalid)
- Intermediate tables: Migration, Quarterly Sums, Average Migration Matrix, MMULT Results

## 3. Exposure at Default (EAD) Model

The EAD model projects the exposure at default over future periods, accounting for loan amortization, repayments, and facility types.

### Data Loading and Preprocessing (EADmodel.py)

1. **Load Raw Data**:
   - File: `worktemplates/Rawdata.xlsx`
   - Header row: Row 1
   - Columns include: Account ID, Reporting Date, Loan Disbursement Date, Loan Maturity Date, Tenor (Months), Outstanding Balance (₦), Credit/Sanction Limit (₦), Types of facilities, Effective Interest rate (%), Repayment Frequency in a Year, etc.

2. **Preprocess Data**:
   - Clean column names: Replace \n with space, strip
   - Convert dates: Reporting Date, Loan Disbursement Date, Loan Maturity Date
   - ADJ Maturity Date: Loan Maturity Date + 7 days
   - Tenor (Months): If not present, calculate from Tenor (Days) / 30.417
   - Tenor To Maturity (Months): max(0, (ADJ Maturity Date - Reporting Date).days / 30.417)
   - MATURITY CHECKER: "NOT MATURED" if ADJ Maturity Date > Reporting Date, else "MATURED"
   - Numeric cleanups: Outstanding Balance, Credit/Sanction Limit
   - Undrawn Overdraft: For overdrafts, if Credit > Outstanding, Credit - Outstanding, else 0
   - Effective Rate Clean: Convert to decimal (divide by 100 if >1)
   - PERIODIC EIR: (1 + Effective Rate Clean)^(1/12) - 1
   - TERM IN FORCE: (Reporting Date - Loan Disbursement Date).days / 30.417
   - REPAYMENT PATTERN: If Repayment Frequency >0, 12 / Frequency, else NaN
   - NUMBER OF PAYMENTS PER MONTH: floor(Tenor (Months) / REPAYMENT PATTERN) if both >0
   - OUTSTANDING BALANCE INCLUDING UNDRAWN FOR ODs: For overdrafts, Outstanding + 0.20 * Undrawn, else Outstanding

3. **PMT Calculation**:
   - For matured loans: Outstanding Balance
   - For overdrafts/bullets: 0
   - Else: PMT(PERIODIC EIR, Tenor To Maturity, Outstanding Balance)
   - PMT formula: PV * r * (1+r)^n / ((1+r)^n - 1)

### EAD Projection Logic

1. **Projection Setup**:
   - Projection dates: 13 months forward from Reporting Date, monthly end dates
   - Projection columns: Date strings like "31-Oct-24"

2. **Per-Account Projection**:
   - For each account:
     - Get periodic_r, start_bal, pmta (PMT), adjm (ADJ Maturity Date), term_in_force, repayment_interval, loan_type, matured_flag
     - prev_bal = start_bal
     - For each projection period:
       - If past maturity: 0
       - bal_after_interest = prev_bal * (1 + periodic_r)
       - payment_due = 0
       - If repayment due (based on term_in_force + period % repayment_interval == 0) and not overdraft/bullet: payment_due = pmta
       - If bullet and at maturity: payment_due = bal_after_interest
       - next_bal = max(0, bal_after_interest - payment_due)
       - If at maturity: next_bal = 0
       - Store next_bal in projection column

3. **Output**:
   - Enriched DataFrame with all derived columns and 13 projection columns
   - Exported to `worktemplates/EAD_Term_Structure_Output.xlsx`

## 4. Expected Credit Loss (ECL) Model

The ECL model combines PD, LGD, EAD, and discount factors to calculate expected credit losses, weighted by scenarios.

### Data Loading (ECLmodel.py)

1. **Load Files**:
   - Raw: `worktemplates/Rawdata.xlsx`
   - EAD: `worktemplates/EAD_Term_Structure_Output.xlsx`
   - DF: `worktemplates/Discount_Factors.xlsx`
   - PD: `worktemplates/PD_results_final.xlsx` (scenarios: Base, Best, Worse)
   - LGD: `worktemplates/LGD_Final.xlsx`
   - SLGD: `worktemplates/SecuredLGD.xlsx`
   - Staging: `worktemplates/Staging.xlsx`

2. **Load PD Scenarios**:
   - Try to find sheets matching scenario names (case-insensitive)
   - Normalize columns

3. **Load LGD**:
   - Find sector and LGD columns
   - Convert LGD to decimal, clamp to 0.5-0.9, fallback 0.53

4. **Load SLGD**:
   - From SLGDinput.py: Load secured LGD, preprocess with repayment freq and collateral lookups

5. **Load Staging**:
   - If exists, load FINAL STAGE column

### ECL Calculation per Account

1. **Per-Account Loop**:
   - Get account_id, outstanding, sector, stage (from raw or staging)
   - Get lgd_val (unsecured), slgd_val (secured)
   - For each period (0-12):
     - ead = get_ead(account_id, period)
     - df = get_df(account_id, period)
     - weighted_pd_lgd = 0
     - For each scenario (Base:0.5, Best:0.25, Worse:0.25):
       - pd_val = get_pd(sector, scenario, period)
       - If stage == 3: pd_val = 1.0
       - weighted_pd_lgd += weight * (pd_val * lgd_val)
     - ecl_t = ead * df * weighted_pd_lgd
   - Total ECL by stage:
     - Stage 1: sum(ecl_periods[:12])
     - Stage 2: sum(ecl_periods)
     - Stage 3: outstanding * slgd_val * lgd_val
   - If matured: ECL = 0

2. **Aggregations**:
   - ECL by Segment: Pivot by Business Sector and Stage, sum Outstanding and ECL
   - ECL by Stage: Group by IFRS 9 STAGE, sum Outstanding and ECL, calculate %

### ECL Output
- ECL Summary: Per-account ECL with period breakdowns
- ECL by Segment: Aggregated by sector
- ECL by Stage: Aggregated by stage

## 5. Staging Model

The Staging model determines IFRS 9 stages (1, 2, 3) based on performance classifications and days past due.

### Staging Logic (staging.py)

1. **Data Loading**:
   - Load PD input, preprocess

2. **Create Staging Table**:
   - **Columns**: S/n, Account ID, Account Names, Outstanding Balance (₦), PERFORMANCE CLASS (31-Mar-25), DPD (31-Mar-25), FINAL QTR STAGE (31-Mar-25), PERFORMANCE CLASS (30-Jun-25), DPD (30-Jun-25), FINAL QTR STAGE (30-Jun-25), PROBATIONARY STAGING, FINAL STAGE

3. **Mappings**:
   - **map_performance_class**: 'Performing' -> 1, 'Watchlist' -> 2, else 3
   - **map_dpd**: DPD <=30 ->1, <=89 ->2, else 3

4. **Quarter Calculations**:
   - Q1 (31-Mar-25):
     - PERFORMANCE CLASS: Map from 'Performance classification'
     - DPD: Map from 'Days past Due (DPD)'
     - FINAL QTR STAGE: max(PERFORMANCE CLASS, DPD)
   - Q2 (30-Jun-25):
     - PERFORMANCE CLASS: From 'Performance classification 2' or fallback to Q1 or derive from DPD
     - DPD: From 'Days past Due (DPD)' or 'Days Past Due after qtr 1'
     - FINAL QTR STAGE: max(PERFORMANCE CLASS, DPD)
   - PROBATIONARY STAGING: FINAL QTR STAGE (31-Mar-25) - 1 (min 0)
   - FINAL STAGE: max(FINAL QTR STAGE (30-Jun-25), PROBATIONARY STAGING)

### Staging Output
- Staging table with stages per account for Q1, Q2, and final

## Summary of Key Formulas

- **PD Migration**: Sum Outstanding Balance by sector/status/quarter, apply FLI scalars
- **LGD**: Transition matrix powers for cure/recovery/default rates, Unsecured LGD = (1 - cure) * (1 - redefault)
- **EAD Projection**: Amortization with interest accrual, repayments at intervals, maturity handling
- **ECL**: ECL_t = EAD_t * DF_t * Σ(weight_scenario * PD_scenario_t * LGD)
- **Staging**: Stage = max(Performance Class, DPD mapping)

All models use historical data to project forward, with fallbacks for missing values and clamps for reasonableness.
