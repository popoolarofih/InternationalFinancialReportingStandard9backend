import pandas as pd
import numpy as np
import sys
import os

# Add the parent directory to sys.path to import from ifrsmodel.PD
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ifrsmodel.PD.pdinput import load_pd_input, preprocess_pd_data
from ifrsmodel.PD.PDmodel import calculate_pd_migration
from ifrsmodel.PD.PDmigration import calculate_total_year_sum
from ifrsmodel.PD.PDtransition import (
    calculate_cumulative_pds,
    calculate_conditional_pds,
    calculate_conditional_pds_monthly,
    calculate_scaled_conditional_pds_monthly,
    calculate_scaled_marginal_pds_monthly,
    calculate_marginal_pds_for_all_scenarios,
    export_pd_results
)
from ifrsmodel.FLI_model.fli_model import get_fli_model
from typing import Dict, Any

def main(reporting_date: str = None, pd_input_path: str = None, fli_file_path: str = None, fli_scalars: Dict[str, Any] = None):
    # Load and preprocess data
    df = load_pd_input(file_path=pd_input_path or 'worktemplates/pd_input.xlsx', header_row=1, reporting_date=reporting_date)
    df = preprocess_pd_data(df)

    # Make sectors dynamic
    sectors = sorted(df['Business sector'].dropna().unique().tolist())

    performing_statuses = ['Performing', 'Default']
    statuses = ['Performing', 'Watchlist', 'Default']

    # Use dynamic quarters based on reporting date if provided
    if reporting_date:
        start_date = pd.Timestamp(reporting_date)
        quarters = []
        for i in range(4):  # Generate 4 quarters
            quarters.append(start_date + pd.offsets.QuarterEnd(i))
    else:
        # Fallback to default quarters
        quarters = [
            pd.Timestamp('2024-09-30'),
            pd.Timestamp('2024-12-31'),
            pd.Timestamp('2025-03-31'),
            pd.Timestamp('2025-06-30'),
        ]

    # Calculate migration table from PDmodel
    migration_df = calculate_pd_migration(df, sectors, performing_statuses, quarters)

    # Calculate cumulative PDs from PDtransition
    cumulative_pd_df = calculate_cumulative_pds(df, sectors, quarters)

    # Calculate conditional PDs
    conditional_pd_df = calculate_conditional_pds(cumulative_pd_df)

    # Calculate conditional monthly PDs
    conditional_monthly_df = calculate_conditional_pds_monthly(conditional_pd_df)

    # Load FLI scalars
    if fli_scalars is not None:
        # Use provided FLI scalars from database
        fli_scalars_dict = fli_scalars
        # Extract the WEIGHTED SCALARS list for PD scaling
        weighted_scalars = fli_scalars_dict.get('WEIGHTED SCALARS', [1.0] * 12)
    else:
        fli_path = fli_file_path or r"worktemplates\Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx"
        try:
            fli_model = get_fli_model(fli_path)
            fli_scalars_dict = fli_model.get('fli_scalar_weights_per_qrt', {})
            weighted_scalars = fli_scalars_dict.get('WEIGHTED SCALARS', [1.0] * 12)
        except Exception as e:
            print(f"Failed to load FLI scalars: {e}")
            fli_scalars_dict = {}
            weighted_scalars = [1.0] * 12

    # Calculate scaled conditional monthly PDs
    scaled_conditional_df = calculate_scaled_conditional_pds_monthly(conditional_monthly_df, weighted_scalars)

    # Calculate scaled marginal PDs
    scaled_marginal_df = calculate_scaled_marginal_pds_monthly(scaled_conditional_df)

    # Calculate marginal PDs for all scenarios
    marginal_pds_dict = calculate_marginal_pds_for_all_scenarios(conditional_monthly_df, fli_scalars_dict, None)

    # Save all results to Excel
    output_file = 'worktemplates/PD_results_final.xlsx'
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Preprocessed data
        df.to_excel(writer, sheet_name='Preprocessed Data', index=False)

        # Migration table
        migration_df.to_excel(writer, sheet_name='Migration Table', index=True)

        # Cumulative PDs
        cumulative_pd_df.to_excel(writer, sheet_name='Cumulative PDs', index=True)

        # Conditional PDs
        conditional_pd_df.to_excel(writer, sheet_name='Conditional PDs', index=True)

        # Conditional Monthly PDs
        conditional_monthly_df.to_excel(writer, sheet_name='Conditional Monthly PDs', index=True)

        # Scaled Conditional Monthly PDs
        scaled_conditional_df.to_excel(writer, sheet_name='Scaled Conditional Monthly', index=True)

        # Scaled Marginal PDs
        scaled_marginal_df.to_excel(writer, sheet_name='Scaled Marginal PDs', index=True)

        # Marginal PDs for each scenario
        for scenario_name, df_scenario in marginal_pds_dict.items():
            sheet_name = scenario_name.replace(' ', '_').replace('PDs', '').strip('_')
            df_scenario.to_excel(writer, sheet_name=sheet_name, index=True)

        # Migration matrices for each sector (total year sum)
        for sector in sectors:
            total_year_matrix = calculate_total_year_sum(df, sector, statuses, quarters)
            sheet_name = f'Matrix_{sector[:20]}'  # Truncate sector name if too long
            total_year_matrix.to_excel(writer, sheet_name=sheet_name, index=True)

    print(f"All results saved to {output_file}")

if __name__ == "__main__":
    main()
