import pandas as pd
import sqlite3
import os
from collections import defaultdict

DATABASE_PATH = 'crypto_data.db'
TABLE_NAME = 'session_summary'
LOOKAHEAD_PERIOD = 5 # Number of subsequent sessions to check for retest

def load_session_summary_data(db_path, table_name):
    """Loads and sorts session summary data from the SQLite database."""
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql_query(query, conn)
        conn.close()

        required_columns = ['Date', 'Sessions', 'SessionStart', 'SessionEnd',
                            'SessionLow', 'SessionHigh', 'SessionClose', 'IB_Low']
        if not all(col in df.columns for col in required_columns):
            print(f"Error: Missing one or more required columns: {required_columns}")
            missing = [col for col in required_columns if col not in df.columns]
            print(f"Missing columns: {missing}")
            return None

        # Convert timestamp columns to datetime objects
        for col in ['SessionStart', 'SessionEnd']:
            df[col] = pd.to_datetime(df[col])
        df['Date'] = pd.to_datetime(df['Date']).dt.date

        # Sort data chronologically
        df = df.sort_values(by=['Date', 'SessionStart']).reset_index(drop=True)
        print(f"Loaded and sorted {len(df)} rows from {table_name}.")
        # print(f"Columns found: {df.columns.tolist()}")
        return df

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during data loading: {e}")
        return None

def analyze_ib_low_retest(df, lookahead=LOOKAHEAD_PERIOD):
    """Analyzes the probability of IB_Low retest after NY close below IB."""
    if df is None:
        print("Error: DataFrame is None. Cannot perform analysis.")
        return None

    # Filter for New York sessions
    ny_sessions = df[df['Sessions'] == 'NewYork'].copy()

    # Identify trigger sessions (NY Close < IB_Low)
    # Ensure IB_Low is numeric and handle potential NaNs
    ny_sessions['IB_Low'] = pd.to_numeric(ny_sessions['IB_Low'], errors='coerce')
    ny_sessions.dropna(subset=['IB_Low', 'SessionClose'], inplace=True) # Drop rows where IB_Low or SessionClose is NaN
    trigger_sessions = ny_sessions[ny_sessions['SessionClose'] < ny_sessions['IB_Low']]

    total_triggers = len(trigger_sessions)
    if total_triggers == 0:
        print("No trigger sessions (New York close < IB_Low) found.")
        return None

    print(f"Found {total_triggers} trigger sessions (NY Close < IB_Low).")

    retest_counts = defaultdict(int)
    no_retest_count = 0
    session_sequence = ['Asia', 'London', 'NewYork']

    for index, trigger_row in trigger_sessions.iterrows():
        trigger_ib_low = trigger_row['IB_Low']
        trigger_df_index = df.index[df['SessionStart'] == trigger_row['SessionStart']].tolist()[0] # Find original index

        retest_found = False
        for k in range(1, lookahead + 1):
            next_session_index = trigger_df_index + k
            if next_session_index >= len(df):
                # Reached end of data for this trigger
                break

            next_session_row = df.iloc[next_session_index]
            session_low = next_session_row['SessionLow']
            session_high = next_session_row['SessionHigh']

            # Check for retest condition
            if session_low <= trigger_ib_low <= session_high:
                retest_counts[k] += 1
                retest_found = True
                break # Stop checking further sessions for this trigger

        if not retest_found:
            no_retest_count += 1

    # --- Calculate and Print Probabilities ---
    print("\\n--- IB_Low Retest Probability Analysis ---")
    print(f"Trigger: New York session closes below IB_Low")
    print(f"Lookahead Period: {lookahead} sessions")
    print(f"Total Trigger Events: {total_triggers}\\n")

    # Determine typical session names for the table
    trigger_ny_index = session_sequence.index('NewYork')
    session_names_in_order = []
    for k in range(1, lookahead + 1):
        session_index = (trigger_ny_index + k) % len(session_sequence)
        session_names_in_order.append(session_sequence[session_index])

    # Print Markdown Table Header
    print("| Subsequent Session | Session Name (Typical) | Probability of First Retest |")
    print("| :----------------- | :--------------------- | :-------------------------- |")

    total_probability = 0
    for k in range(1, lookahead + 1):
        probability = (retest_counts[k] / total_triggers) * 100 if total_triggers > 0 else 0
        total_probability += probability
        session_name = session_names_in_order[k-1]
        print(f"| Session +{k:<11} | {session_name:<22} | {probability:>26.2f}% |")

    no_retest_probability = (no_retest_count / total_triggers) * 100 if total_triggers > 0 else 0
    total_probability += no_retest_probability
    print(f"| **No Retest**      | (Within {lookahead} Sessions)    | {no_retest_probability:>26.2f}% |")
    print(f"| **Total**          |                        | {total_probability:>26.2f}% |") # Should be close to 100%

    return retest_counts, no_retest_count


if __name__ == "__main__":
    print("Starting IB Low Retest Analysis...")
    session_df = load_session_summary_data(DATABASE_PATH, TABLE_NAME)

    if session_df is not None:
        results = analyze_ib_low_retest(session_df, lookahead=LOOKAHEAD_PERIOD)
        if results:
            print("\\nAnalysis complete.")
        else:
            print("\\nAnalysis could not be completed.")
    else:
        print("Failed to load data. Exiting analysis.") 