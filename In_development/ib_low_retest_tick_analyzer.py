import pandas as pd
import sqlite3
import os
import numpy as np
from datetime import timedelta

# --- Configuration ---
DATABASE_PATH = 'crypto_data.db'
SUMMARY_TABLE_NAME = 'session_summary'
TICK_DATA_PATH = 'BTCUSDT_PERP_BINANCE_normalized.txt'
# Required columns from tick data (Corrected to match file structure)
TICK_DATA_COLS = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'BidVolume', 'AskVolume']
IB_DURATION_HOURS = 1 # Initial Balance duration
TARGET_SESSION = 'NewYork' # Session to analyze
# ANALYSIS_TIMEFRAME = '15T' # <<< No longer needed

def load_session_summary_data(db_path, table_name):
    """Loads and sorts session summary data from the SQLite database."""
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return None
    try:
        conn = sqlite3.connect(db_path)
        # Select only necessary columns
        query = f"SELECT Date, Sessions, SessionStart, SessionEnd, SessionClose, IB_Low FROM {table_name}"
        df = pd.read_sql_query(query, conn)
        conn.close()

        required_summary_cols = ['Date', 'Sessions', 'SessionStart', 'SessionEnd', 'SessionClose', 'IB_Low']
        if not all(col in df.columns for col in required_summary_cols):
            print(f"Error: Missing one or more required summary columns: {required_summary_cols}")
            missing = [col for col in required_summary_cols if col not in df.columns]
            print(f"Missing columns: {missing}")
            return None

        # Convert relevant columns
        for col in ['SessionStart', 'SessionEnd']:
            df[col] = pd.to_datetime(df[col])
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        df['IB_Low'] = pd.to_numeric(df['IB_Low'], errors='coerce') # Ensure numeric

        # Sort data chronologically
        df = df.sort_values(by=['Date', 'SessionStart']).reset_index(drop=True)
        print(f"Loaded {len(df)} rows from {table_name}.")
        return df
    except Exception as e:
        print(f"An error occurred loading summary data: {e}")
        return None

# def load_tick_data(tick_file_path, required_cols): # <<< REMOVE this function
#     ...

# def resample_to_ohlc(tick_df, timeframe): # <<< REMOVE this function
#     ...

# Modify the main analysis function
def find_ny_close_below_ib(summary_df, target_session):
    """Identifies and reports NY sessions closing below IB_Low."""
    if summary_df is None:
        print("Error: Missing summary data.")
        return None

    # 1. Filter for Target Sessions and Condition
    trigger_sessions = summary_df[
        (summary_df['Sessions'] == target_session) &
        (summary_df['SessionClose'] < summary_df['IB_Low']) &
        summary_df['IB_Low'].notna()
    ].copy()

    total_triggers = len(trigger_sessions)

    # 2. Report Results
    print(f"\n--- Analysis: {target_session} Sessions Closing Below IB_Low ---")

    if total_triggers == 0:
        print(f"No {target_session} sessions found closing below their IB_Low.")
        return None

    print(f"Found {total_triggers} instances where the {target_session} session closed below its IB_Low.\n")
    print("Details of identified sessions:")
    # Select and print relevant columns
    print(trigger_sessions[['Date', 'SessionStart', 'SessionClose', 'IB_Low']].to_string(index=False))

    return trigger_sessions # Return the DataFrame with identified sessions

if __name__ == "__main__":
    print(f"Starting Analysis: Identify {TARGET_SESSION} sessions closing below IB_Low...")
    summary_df = load_session_summary_data(DATABASE_PATH, SUMMARY_TABLE_NAME)
    # tick_df = load_tick_data(TICK_DATA_PATH, TICK_DATA_COLS) # <<< REMOVE

    if summary_df is not None:
        # ohlc_df = resample_to_ohlc(tick_df, ANALYSIS_TIMEFRAME) # <<< REMOVE
        # if ohlc_df is not None: # <<< REMOVE
        # Perform the simplified analysis
        identified_sessions = find_ny_close_below_ib(summary_df, TARGET_SESSION)
        if identified_sessions is not None:
             print("\nAnalysis complete.")
        else:
             print("\nAnalysis completed, but no matching sessions found or an error occurred.")
        # else: # <<< REMOVE
        #     print("\nFailed to resample tick data. Exiting analysis.") # <<< REMOVE
    else:
        print("\nFailed to load summary data. Exiting analysis.") 