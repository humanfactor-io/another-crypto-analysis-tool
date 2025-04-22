"""
Backtests the Monday Range Rotation strategy using session summary data.
Calculates the frequency of weeks where price touches both the Monday High and Monday Low.
"""
import pandas as pd
import numpy as np
import sqlite3
import os
import datetime

# --- Constants ---
DATABASE_PATH = 'crypto_data.db'
KEY_LEVELS_TABLE = 'btc_key_levels'
SESSION_SUMMARY_TABLE = 'session_summary'

# --- Data Loading & Preparation ---
def load_and_prepare_data(db_path, key_levels_table, summary_table):
    """Loads key levels and session summary, merges, and prepares them."""
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)
        
        # Check if tables exist
        query_levels = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{key_levels_table}';"
        query_summary = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{summary_table}';"
        levels_exists = pd.read_sql(query_levels, conn).shape[0] > 0
        summary_exists = pd.read_sql(query_summary, conn).shape[0] > 0

        if not levels_exists:
            print(f"Error: Key levels table '{key_levels_table}' not found.")
            conn.close()
            return None
        if not summary_exists:
            print(f"Error: Session summary table '{summary_table}' not found.")
            conn.close()
            return None
            
        # Load Key Levels (parse SessionStartUTC)
        key_cols = ['SessionStartUTC', 'SessionDate', 'MondayHigh', 'MondayLow']
        df_levels = pd.read_sql(f'SELECT {", ".join(key_cols)} FROM {key_levels_table}', conn, parse_dates=['SessionStartUTC'])
        df_levels.rename(columns={'SessionStartUTC': 'SessionStart'}, inplace=True) # Rename for merge
        df_levels['SessionDate'] = pd.to_datetime(df_levels['SessionDate']).dt.date # Ensure date object
        print(f"Loaded {len(df_levels)} rows from {key_levels_table}.")

        # Load Session Summary (parse SessionStart)
        summary_cols = ['SessionStart', 'SessionHigh', 'SessionLow']
        df_summary = pd.read_sql(f'SELECT {", ".join(summary_cols)} FROM {summary_table}', conn, parse_dates=['SessionStart'])
        print(f"Loaded {len(df_summary)} rows from {summary_table}.")

        conn.close()

        # Ensure SessionStart is the key for merging
        df_levels['SessionStart'] = pd.to_datetime(df_levels['SessionStart'])
        df_summary['SessionStart'] = pd.to_datetime(df_summary['SessionStart'])

        # Merge data
        df_merged = pd.merge(df_summary, df_levels, on='SessionStart', how='inner')
        if df_merged.empty:
             print("Error: Merge resulted in empty DataFrame. Check SessionStart alignment.")
             return None
             
        print(f"Merged data shape: {df_merged.shape}")

        # Convert relevant columns to numeric
        for col in ['SessionHigh', 'SessionLow', 'MondayHigh', 'MondayLow']:
            df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')
        df_merged.dropna(subset=['MondayHigh', 'MondayLow', 'SessionHigh', 'SessionLow'], inplace=True)
        if df_merged.empty:
            print("Error: Dataframe empty after dropping rows with missing levels/prices.")
            return None

        # Add Week and DayOfWeek columns (Monday=0, Sunday=6)
        # Use SessionStart which is already datetime
        df_merged['WeekOfYear'] = df_merged['SessionStart'].dt.strftime('%Y-%U') # Week starts Sunday by default, use %W for Monday
        df_merged['WeekOfYearMon'] = df_merged['SessionStart'].dt.strftime('%Y-%W') # Use Monday start for grouping
        df_merged['DayOfWeek'] = df_merged['SessionStart'].dt.dayofweek

        print("Data preparation complete.")
        return df_merged

    except Exception as e:
        print(f"An error occurred during data loading/preparation: {e}")
        return None

# --- Backtesting Logic ---
def backtest_monday_rotation(df):
    """Performs the Monday rotation backtest, checking only Tue-Fri."""
    if df is None:
        print("Error: Input DataFrame is None.")
        return

    # --- FIX: Filter for Tuesday (1) to Friday (4) only ---
    df_analysis = df[df['DayOfWeek'].isin([1, 2, 3, 4])].copy()
    if df_analysis.empty:
        print("No data available for Tuesday-Friday to analyze.")
        return
    # --- END FIX ---
        
    # Flag sessions touching Monday's extremes
    df_analysis['TouchedMondayHigh'] = df_analysis['SessionHigh'] >= df_analysis['MondayHigh']
    df_analysis['TouchedMondayLow'] = df_analysis['SessionLow'] <= df_analysis['MondayLow']

    # Group by week (using Monday start week identifier)
    weekly_touches = df_analysis.groupby('WeekOfYearMon')[['TouchedMondayHigh', 'TouchedMondayLow']].any()

    # Identify weeks with full rotation (touched both high and low)
    weekly_touches['FullRotation'] = weekly_touches['TouchedMondayHigh'] & weekly_touches['TouchedMondayLow']

    # Calculate statistics
    total_weeks_analyzed = len(weekly_touches)
    weeks_with_rotation = weekly_touches['FullRotation'].sum()
    rotation_frequency = (weeks_with_rotation / total_weeks_analyzed) * 100 if total_weeks_analyzed > 0 else 0

    print("\n--- Monday Range Rotation Backtest Results (Tue-Fri) ---") # Updated Title
    print(f"Total Weeks Analyzed (with Tue-Fri data): {total_weeks_analyzed}")
    print(f"Weeks with Full Rotation (High & Low Touched Tue-Fri): {weeks_with_rotation}")
    print(f"Frequency of Full Rotation: {rotation_frequency:.2f}%")

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Monday Range Rotation Backtest...")
    prepared_data = load_and_prepare_data(DATABASE_PATH, KEY_LEVELS_TABLE, SESSION_SUMMARY_TABLE)
    
    if prepared_data is not None:
        backtest_monday_rotation(prepared_data)
        print("\nBacktest complete.")
    else:
        print("\nFailed to load or prepare data. Backtest aborted.") 