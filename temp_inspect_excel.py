import pandas as pd

file_path = "worktemplates/Updated FLI  Scenario Weights Inputs - 31.03.25 20250530.xlsx"
sheet_name = "Scenario Weight Historical Data"

df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
print(df.head(10))
