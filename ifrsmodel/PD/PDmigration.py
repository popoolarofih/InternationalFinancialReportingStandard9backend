import pandas as pd
import logging
from ifrsmodel.PD.pdinput import load_pd_input, preprocess_pd_data, clean_inputs_with_helpers, enrich_with_db_mappings, merge_write_off_data
from ifrsmodel.FLI_model.fli_model import get_fli_model

def calculate_pd_migration_matrix(df, sector, quarter_date, statuses):
    """
    Calculate the PD migration matrix for a given sector and quarter.

    Parameters:
    - df: preprocessed PD input DataFrame
    - sector: business sector string
    - quarter_date: reporting date as pd.Timestamp or string
    - statuses: list of statuses (e.g., ['Performing', 'Watchlist', 'Default'])

    Returns:
    - migration_matrix: pd.DataFrame with index=FROM statuses, columns=TO statuses, values=sum of Outstanding Balance
    """
    # Initialize empty DataFrame
    migration_matrix = pd.DataFrame(index=statuses, columns=statuses, data=0.0)

    # Convert quarter_date to string format matching Reporting Date
    if isinstance(quarter_date, pd.Timestamp):
        quarter_str = quarter_date.strftime('%Y-%m-%d')
    else:
        quarter_str = str(quarter_date)

    for from_status in statuses:
        for to_status in statuses:
            filtered = df[
                (df['Business sector'] == sector) &
                (df['Performance classification 2'] == from_status) &
                (df['PD Performance after qtr 1'] == to_status) &
                (df['Reporting Date'].dt.strftime('%Y-%m-%d') == quarter_str)
            ]
            sum_val = filtered['Outstanding Balance (₦)'].sum() if 'Outstanding Balance (₦)' in df.columns else 0.0
            migration_matrix.at[from_status, to_status] = sum_val

    # Add row totals
    migration_matrix['TOTAL'] = migration_matrix.sum(axis=1)
    # Add column totals
    total_row = migration_matrix.sum(axis=0)
    total_row.name = 'TOTAL'
    migration_matrix = pd.concat([migration_matrix, total_row.to_frame().T])

    return migration_matrix

def calculate_total_year_sum(df, sector, statuses, quarters):
    """
    Calculate the TOTAL YEAR'S SUM migration matrix for a given sector,
    aggregating all quarters in the year.

    Parameters:
    - df: preprocessed PD input DataFrame
    - sector: business sector string
    - statuses: list of statuses (e.g., ['Performing', 'Watchlist', 'Default'])
    - quarters: list of pd.Timestamp or string representing quarters

    Returns:
    - total_year_matrix: pd.DataFrame with index=FROM statuses, columns=TO statuses, values=sum of Outstanding Balance across all quarters
    """
    # Initialize empty DataFrame
    total_year_matrix = pd.DataFrame(index=statuses, columns=statuses, data=0.0)

    quarter_strs = [q.strftime('%Y-%m-%d') if isinstance(q, pd.Timestamp) else str(q) for q in quarters]

    for from_status in statuses:
        for to_status in statuses:
            sum_val = 0.0
            for quarter_str in quarter_strs:
                filtered = df[
                    (df['Business sector'] == sector) &

                    (df['Performance classification 2'] == from_status) &
                    (df['PD Performance after qtr 1'] == to_status) &
                    (df['Reporting Date'].dt.strftime('%Y-%m-%d') == quarter_str)
                ]
                sum_val += filtered['Outstanding Balance (₦)'].sum() if 'Outstanding Balance (₦)' in df.columns else 0.0
            total_year_matrix.at[from_status, to_status] = sum_val

    # Add row totals
    total_year_matrix['TOTAL'] = total_year_matrix.sum(axis=1)
    # Add column totals
    total_row = total_year_matrix.sum(axis=0)
    total_row.name = 'TOTAL'
    total_year_matrix = pd.concat([total_year_matrix, total_row.to_frame().T])

    # Check default rate and set to 0.001% floor if zero, then re-normalize row
    total_outstanding = total_year_matrix.loc[:, 'TOTAL'].sum()
    default_outstanding = total_year_matrix.loc['Performing', 'Default'] if 'Performing' in total_year_matrix.index and 'Default' in total_year_matrix.columns else 0.0
    default_rate = default_outstanding / total_outstanding if total_outstanding > 0 else 0.0
    pd_floor = 0.00002 
    if default_rate == 0:
        # Set floor PD in migration matrix
        total_year_matrix.at['Performing', 'Default'] = pd_floor * total_outstanding
        # Recalculate the row sum excluding the default column
        row_sum_excl_default = total_year_matrix.loc['Performing', total_year_matrix.columns != 'Default'].sum()
        # Adjust other probabilities proportionally to sum to (1 - pd_floor)
        for col in total_year_matrix.columns:
            if col != 'Default' and col != 'TOTAL':
                original_val = total_year_matrix.at['Performing', col]
                if row_sum_excl_default > 0:
                    adjusted_val = original_val * (1 - pd_floor) / row_sum_excl_default
                else:
                    adjusted_val = 0.0
                total_year_matrix.at['Performing', col] = adjusted_val
        # Recalculate row total
        total_year_matrix.at['Performing', 'TOTAL'] = total_year_matrix.loc['Performing', total_year_matrix.columns != 'TOTAL'].sum()

    return total_year_matrix

def generate_40_quarter_matrices(df, sectors, statuses, start_date=pd.Timestamp('2024-09-30'), num_quarters=40):
    """
    Generate migration matrices for 40 quarters.
    """
    matrices = {}
    for sector in sectors:
        sector_matrices = {}
        for i in range(num_quarters):
            quarter_date = start_date + pd.offsets.QuarterEnd(i)
            matrix = calculate_pd_migration_matrix(df, sector, quarter_date, statuses)
            sector_matrices[quarter_date.strftime('%Y-%m-%d')] = matrix
        matrices[sector] = sector_matrices
    logging.info(f"Generated 40-quarter matrices for {len(sectors)} sectors.")
    return matrices



def calculate_monthly_conditional_pd(migration_matrix):
    """
    Calculate monthly conditional PDs from quarterly migration matrix.
    """
    # Assume quarterly to monthly by dividing by 3
    monthly_pd = migration_matrix / 3
    return monthly_pd

def calculate_monthly_marginal_pd(migration_matrix):
    """
    Calculate monthly marginal PDs.
    """
    # Placeholder: Marginal PD as cumulative
    marginal_pd = migration_matrix.cumsum(axis=1)
    return marginal_pd

def apply_fli_scalars_to_pd(migration_matrix, fli_scalars):
    """
    Apply FLI scalars for scenario weighting.
    """
    scenario_weighted = {}
    for scenario in ['Base Scenario', 'Best Scenario', 'Worst Scenario']:
        weight = fli_scalars.get(scenario, [1.0])[0] if isinstance(fli_scalars.get(scenario, None), list) else 1.0
        scenario_weighted[scenario] = migration_matrix * weight
    # Weighted scalar
    weighted_scalars = fli_scalars.get('WEIGHTED SCALARS', [1.0])
    scenario_weighted['Weighted'] = migration_matrix * weighted_scalars[0]
    return scenario_weighted

def package_pd_outputs_as_dict(matrices, monthly_pd, marginal_pd, scenario_weighted):
    """
    Package outputs as dictionary for downstream models.
    """
    outputs = {
        'migration_matrices': matrices,
        'monthly_conditional_pd': monthly_pd,
        'monthly_marginal_pd': marginal_pd,
        'scenario_weighted_pd': scenario_weighted
    }
    logging.info("Packaged PD outputs as dictionary.")
    return outputs

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    df = load_pd_input(header_row=1)
    df = preprocess_pd_data(df)

    # Dynamic sectors
    sectors = sorted(df['Business sector'].dropna().unique().tolist())
    logger.info(f"Dynamic sectors: {sectors}")

    statuses = ['Performing', 'Watchlist', 'Default']

    # Generate 40 quarters
    start_date = pd.Timestamp('2024-09-30')
    num_quarters = 40
    quarters = [start_date + pd.offsets.QuarterEnd(i) for i in range(num_quarters)]
    logger.info(f"Generated {num_quarters} quarters starting from {start_date.strftime('%Y-%m-%d')}")

    # Load FLI scalars
    fli_file_path = r"worktemplates\Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx"
    try:
        fli_model = get_fli_model(fli_file_path)
        fli_scalars = fli_model.get('fli_scalar_weights_per_qrt', {})
        logger.info("FLI scalars loaded.")
    except Exception as e:
        logger.warning(f"Failed to load FLI scalars: {e}")
        fli_scalars = {}

    # Generate 40-quarter matrices
    matrices = generate_40_quarter_matrices(df, sectors, statuses, start_date, num_quarters)

    # For demonstration, take the first matrix and calculate monthly PDs
    sample_sector = sectors[0]
    sample_matrix = matrices[sample_sector][quarters[0].strftime('%Y-%m-%d')]

    monthly_conditional_pd = calculate_monthly_conditional_pd(sample_matrix)
    monthly_marginal_pd = calculate_monthly_marginal_pd(sample_matrix)

    # Apply FLI scalars
    scenario_weighted = apply_fli_scalars_to_pd(sample_matrix, fli_scalars)

    # Package outputs
    outputs = package_pd_outputs_as_dict(matrices, monthly_conditional_pd, monthly_marginal_pd, scenario_weighted)

    print("Sample Monthly Conditional PD:")
    print(monthly_conditional_pd)
    print("\nSample Scenario Weighted PD:")
    for scenario, matrix in scenario_weighted.items():
        print(f"{scenario}:")
        print(matrix)
        print("\n")
    
