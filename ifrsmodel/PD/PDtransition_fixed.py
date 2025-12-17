import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import logging
from ifrsmodel.PD.PDmigration import calculate_total_year_sum, calculate_pd_migration_matrix
from ifrsmodel.PD.pdinput import load_pd_input, preprocess_pd_data
from ifrsmodel.macro_scalars import MacroScalars

logging.basicConfig(level=logging.WARNING)

def map_performance_to_stage(performance_status):
    if performance_status == 'Performing':
        return 1
    elif performance_status == 'Watchlist':
        return 2
    elif performance_status == 'Default':
        return 3
    else:
        return None

def filter_by_stage_horizon(df, stage, max_quarters_stage2=4):
    df = df.copy()
    df['Stage'] = df['Performance classification 2'].apply(map_performance_to_stage)
    df_stage = df[df['Stage'] == stage]

