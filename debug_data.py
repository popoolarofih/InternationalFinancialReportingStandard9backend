import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ifrsmodel.PD.pdinput import load_pd_input, preprocess_pd_data

if __name__ == "__main__":
    df = load_pd_input(header_row=1)
    print(f"Loaded df shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    print(f"First 5 rows:\n{df.head()}")

    df_processed = preprocess_pd_data(df)
    print(f"\nProcessed df shape: {df_processed.shape}")
    print(f"Processed columns: {df_processed.columns.tolist()}")
    print(f"First 5 rows of processed:\n{df_processed.head()}")

    if 'Sector' in df_processed.columns:
        print(f"\nUnique sectors: {df_processed['Sector'].unique()}")
    if 'Performance classification 2' in df_processed.columns:
        print(f"Unique performance classifications: {df_processed['Performance classification 2'].unique()}")
    if 'Reporting Date' in df_processed.columns:
        print(f"Reporting Date range: {df_processed['Reporting Date'].min()} to {df_processed['Reporting Date'].max()}")
