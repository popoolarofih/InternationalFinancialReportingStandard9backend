import pandas as pd
import numpy as np
import os
import logging

def raw_input(file_path='worktemplates/MacroScalars.xlsx'):
    """
    Load the Macro Scalars file and return the ExcelFile object.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found.")
    
    # Load all sheets from the Excel file
    xls = pd.ExcelFile(file_path)
    return xls

class MacroScalars:
    """
    Macro scalars for PD model with adjustable scenario weights.
    """

    def __init__(self, file_path='worktemplates/MacroScalars.xlsx'):
        # Load Excel file
        xls = raw_input(file_path)
        
        # Debug: Read the first few rows of the sheet to inspect
        debug_df = pd.read_excel(xls, sheet_name='MACRO SCALARS', header=None, nrows=15)
        logging.info("First 15 rows of MACRO SCALARS sheet:\n" + str(debug_df))

        # Read scenario weights (row 3, columns C-E)
        weights_df = pd.read_excel(
            xls, 
            sheet_name='MACRO SCALARS',
            header=None,
            skiprows=2,
            nrows=1,
            usecols='C:E'
        )
        
        print("Raw weights data:", weights_df)
        
        weights_df.columns = ['Base', 'Best', 'Worse']
        
        try:
            self.scenario_weights = {
                'Base': float(weights_df['Base'].iloc[0]),
                'Best': float(weights_df['Best'].iloc[0]),
                'Worse': float(weights_df['Worse'].iloc[0])
            }
        except ValueError as e:
            raise ValueError(f"Failed to convert weights to floats: {weights_df.iloc[0].to_dict()}") from e
        
        print("Scenario Weights:", self.scenario_weights)

        # Read quarterly forecast scalars
        self.forecast_scalars = pd.read_excel(
            xls, 
            sheet_name='MACRO SCALARS',
            header=7,
            usecols='B:E'
        )
        self.forecast_scalars.columns = ['Date', 'Base', 'Best', 'Worse']
        self.forecast_scalars = self.forecast_scalars.dropna(subset=['Date', 'Base', 'Best', 'Worse'])

        print("Quarterly Scalars Columns:", self.forecast_scalars.columns)
        print("Quarterly Scalars Data (cleaned):\n", self.forecast_scalars)

        self.forecast_scalars['Date'] = pd.to_datetime(self.forecast_scalars['Date'])

        try:
            self.monthly_forecast_scalars = pd.read_excel(
                xls, 
                sheet_name='MACRO SCALARS',
                skiprows=14,
                usecols='B:G'
            )
            print("Monthly Scalars Columns:", self.monthly_forecast_scalars.columns)
            print("Monthly Scalars Data:\n", self.monthly_forecast_scalars.head())

            expected_monthly_cols = ['Date', 'Period', 'Base_Case', 'Best_Case', 'Worst_Case', 'Scenario_Weighted']
            if len(self.monthly_forecast_scalars.columns) == len(expected_monthly_cols):
                self.monthly_forecast_scalars.columns = expected_monthly_cols
            else:
                print("Warning: Monthly forecast scalars table not found or incorrect format. Skipping monthly data.")
                self.monthly_forecast_scalars = pd.DataFrame()

            if not self.monthly_forecast_scalars.empty:
                self.monthly_forecast_scalars = self.monthly_forecast_scalars.dropna(
                    subset=['Date', 'Period', 'Base_Case', 'Best_Case', 'Worst_Case', 'Scenario_Weighted']
                )
                self.monthly_forecast_scalars['Date'] = pd.to_datetime(self.monthly_forecast_scalars['Date'])
        except Exception as e:
            print(f"Warning: Could not load monthly forecast scalars: {e}. Proceeding without monthly data.")
            self.monthly_forecast_scalars = pd.DataFrame()

    def update_scenario_weights(self, base=None, best=None, worse=None):
        if base is not None:
            self.scenario_weights['Base'] = base
        if best is not None:
            self.scenario_weights['Best'] = best
        if worse is not None:
            self.scenario_weights['Worse'] = worse

        total_weight = sum(self.scenario_weights.values())
        if not np.isclose(total_weight, 1.0, atol=1e-6):
            print(f"Warning: Scenario weights sum to {total_weight:.6f}, not 1.0")

    def calculate_scenario_weighted_scalars(self):
        self.forecast_scalars['Year'] = self.forecast_scalars['Date'].dt.year
        weighted_scalars = {}
        for year in self.forecast_scalars['Year'].unique():
            year_data = self.forecast_scalars[self.forecast_scalars['Year'] == year]
            if year_data.empty:
                continue
            base_weighted = np.average(year_data['Base'])
            best_weighted = np.average(year_data['Best'])
            worse_weighted = np.average(year_data['Worse'])
            weighted_scalar = (
                base_weighted * self.scenario_weights['Base'] +
                best_weighted * self.scenario_weights['Best'] +
                worse_weighted * self.scenario_weights['Worse']
            )
            weighted_scalars[year] = weighted_scalar
        return weighted_scalars

    def get_forecast_npl_ratio(self, date):
        if isinstance(date, str):
            date = pd.to_datetime(date)
        closest_idx = (self.forecast_scalars['Date'] - date).abs().idxmin()
        row = self.forecast_scalars.loc[closest_idx]
        weighted_scalar = (
            row['Base'] * self.scenario_weights['Base'] +
            row['Best'] * self.scenario_weights['Best'] +
            row['Worse'] * self.scenario_weights['Worse']
        )
        return weighted_scalar

    def display_current_setup(self):
        print("=== MACRO SCALARS SETUP ===")
        print("\nScenario Weights:")
        for scenario, weight in self.scenario_weights.items():
            print(f"{scenario}: {weight:.4f} ({weight*100:.2f}%)")
        print(f"\nTotal Weight: {sum(self.scenario_weights.values()):.6f}")
        print("\nForecast Scalars:")
        print(self.forecast_scalars.to_string(index=False))
        print("\nScenario Weighted Scalars:")
        weighted = self.calculate_scenario_weighted_scalars()
        for year, value in weighted.items():
            print(f"{year}: {value:.6f}")
        if not self.monthly_forecast_scalars.empty:
            print("\n=== FORECAST SCALARS FOR PD MIGRATION ===")
            self.display_monthly_forecast_scalars()

    def display_monthly_forecast_scalars(self):
        if self.monthly_forecast_scalars.empty:
            print("\nMonthly Forecast Scalars for PD Migration: Not available")
            return
        print("\nMonthly Forecast Scalars for PD Migration:")
        display_df = self.monthly_forecast_scalars.copy()
        display_df['Date_Str'] = display_df['Date'].dt.strftime('%d-%b-%y')
        summary_df = pd.DataFrame({
            'Period': display_df['Period'],
            'Date': display_df['Date_Str'],
            'Base_Case': display_df['Base_Case'],
            'Worst_Case': display_df['Worst_Case'],
            'Best_Case': display_df['Best_Case'],
            'Scenario_Weighted': display_df['Scenario_Weighted']
        })
        print(summary_df.to_string(index=False))

    def get_scalars_by_scenario(self, scenario_selection):
        """
        Get scalar values based on scenario selection (like Excel dropdown).
        Falls back to quarterly data (expanded to 12 months) if monthly data is missing.
        """
        scenario_options = {
            'Base Case': 'Base',
            'Best Case': 'Best',
            'Worst Case': 'Worse',
            'Scenario Weighted': None
        }
        if not self.monthly_forecast_scalars.empty:
            col_map = {
                'Base Case': 'Base_Case',
                'Best Case': 'Best_Case',
                'Worst Case': 'Worst_Case',
                'Scenario Weighted': 'Scenario_Weighted'
            }
            if scenario_selection not in col_map:
                raise ValueError(f"Invalid scenario selection. Must be one of: {list(col_map.keys())}")
            column_name = col_map[scenario_selection]
            scalars_df = self.monthly_forecast_scalars[self.monthly_forecast_scalars['Period'] > 0]
            return scalars_df[column_name].tolist()
        if scenario_selection == 'Scenario Weighted':
            values = (
                self.forecast_scalars['Base'] * self.scenario_weights['Base'] +
                self.forecast_scalars['Best'] * self.scenario_weights['Best'] +
                self.forecast_scalars['Worse'] * self.scenario_weights['Worse']
            ).tolist()
        else:
            if scenario_selection not in scenario_options:
                raise ValueError(f"Invalid scenario selection. Must be one of: {list(scenario_options.keys())}")
            column_name = scenario_options[scenario_selection]
            values = self.forecast_scalars[column_name].tolist()
        expanded = []
        for v in values:
            expanded.extend([v] * 3)
        if len(expanded) < 12:
            expanded.extend([expanded[-1]] * (12 - len(expanded)))
        return expanded[:12]

    def display_scalars_table(self):
        print("\n=== SCALARS TABLE ===")
        print("Available scenarios: Base Case, Best Case, Worst Case, Scenario Weighted")
        if self.monthly_forecast_scalars.empty:
            print("\nSCALARS values for periods 1-12: Not available")
            return
        scalars_data = self.monthly_forecast_scalars[self.monthly_forecast_scalars['Period'] > 0]
        scalars_table = pd.DataFrame({
            'Period': range(1, 13),
            'Base_Case': scalars_data['Base_Case'].round(2),
            'Best_Case': scalars_data['Best_Case'].round(2),
            'Worst_Case': scalars_data['Worst_Case'].round(2),
            'Scenario_Weighted': scalars_data['Scenario_Weighted'].round(2)
        })
        print("\nSCALARS values for periods 1-12:")
        print(scalars_table.to_string(index=False))

    def simulate_excel_dropdown(self, selected_scenario):
        print(f"\n=== SIMULATING EXCEL DROPDOWN: {selected_scenario} ===")
        try:
            scalar_values = self.get_scalars_by_scenario(selected_scenario)
            print(f"Selected scenario: {selected_scenario}")
            print("Scalar values for periods 1-12:")
            for i, value in enumerate(scalar_values, 1):
                print(f"Period {i}: {value:.2f}")
            return scalar_values
        except ValueError as e:
            print(f"Error: {e}")
            return None

if __name__ == "__main__":
    try:
        macro_scalars = MacroScalars()
        macro_scalars.display_current_setup()
        macro_scalars.display_scalars_table()
        print("\n=== UPDATING WEIGHTS EXAMPLE ===")
        macro_scalars.update_scenario_weights(base=0.5, best=0.3, worse=0.2)
        macro_scalars.display_current_setup()
        print("\n=== FORECAST EXAMPLE ===")
        forecast_date = pd.Timestamp('2025-10-15')
        forecast_value = macro_scalars.get_forecast_npl_ratio(forecast_date)
        print(f"Forecast NPL/Avr NPL Ratio for {forecast_date.date()}: {forecast_value:.4f}")
        print("\n=== EXCEL DROPDOWN SIMULATION ===")
        scenarios = ["Base Case", "Best Case", "Worst Case", "Scenario Weighted"]
        for scenario in scenarios:
            macro_scalars.simulate_excel_dropdown(scenario)
            print()
    except Exception as e:
        print(f"Error in main execution: {e}")
