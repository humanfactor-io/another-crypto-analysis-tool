import pandas as pd
import sqlite3
import os
from collections import defaultdict

DATABASE_PATH = 'crypto_data.db'
TABLE_NAME = 'session_summary'

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
                            'SessionLow', 'SessionHigh', 'SessionOpen'] # Need SessionOpen
        if not all(col in df.columns for col in required_columns):
            print(f"Error: Missing one or more required columns: {required_columns}")
            missing = [col for col in required_columns if col not in df.columns]
            print(f"Missing columns: {missing}")
            return None

        # Convert timestamp columns to datetime objects
        for col in ['SessionStart', 'SessionEnd']:
            df[col] = pd.to_datetime(df[col])
        df['Date'] = pd.to_datetime(df['Date']).dt.date

        # Sort data chronologically FIRST
        df = df.sort_values(by=['Date', 'SessionStart']).reset_index(drop=True)

        # Add Week Identifier (Year-WeekNumber, Monday start)
        # Ensure SessionStart is timezone-naive if it's not already, or handle timezone appropriately
        # Assuming UTC or timezone-naive for simplicity here based on previous context
        df['YearWeek'] = df['SessionStart'].dt.strftime('%Y-%W')

        print(f"Loaded and sorted {len(df)} rows from {table_name}.")
        return df

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during data loading: {e}")
        return None

def analyze_weekly_open_retest(df):
    """Analyzes the probability of the Weekly Open being retested within the same week."""
    if df is None or 'YearWeek' not in df.columns:
        print("Error: DataFrame is None or missing 'YearWeek' column.")
        return None

    retest_counts = defaultdict(int) # Key: session index within week (1=first after open, 2=second after open, etc.)
    no_retest_count = 0
    total_weeks_analyzed = 0

    # Group by the calculated YearWeek
    grouped_by_week = df.groupby('YearWeek')

    for week_id, week_df in grouped_by_week:
        if len(week_df) < 2:
            # Need at least 2 sessions (open + one subsequent) to check for retest
            continue

        total_weeks_analyzed += 1

        # First session of the week determines the Weekly Open
        # Data is already sorted, so iloc[0] is the first session
        first_session = week_df.iloc[0]
        weekly_open_price = first_session['SessionOpen']

        retest_found_this_week = False
        # Iterate through subsequent sessions *within the same week*
        for i in range(1, len(week_df)):
            subsequent_session = week_df.iloc[i]
            session_low = subsequent_session['SessionLow']
            session_high = subsequent_session['SessionHigh']

            # Check for retest condition
            if session_low <= weekly_open_price <= session_high:
                session_index_within_week = i # 0 = first session, 1 = second session, etc.
                retest_counts[session_index_within_week] += 1 # Record retest at index i (i.e., the i+1 session)
                retest_found_this_week = True
                break # Stop checking this week once the first retest is found

        if not retest_found_this_week:
            no_retest_count += 1

    # --- Calculate and Print Probabilities ---
    print("\n--- Weekly Open Retest Probability Analysis ---")
    print(f"Definition: First retest of Monday 00:00 UTC week's Open price.")
    print(f"Scope: Within the same calendar week (Mon-Sun).")
    print(f"Total Complete Weeks Analyzed: {total_weeks_analyzed}\n")

    if total_weeks_analyzed == 0:
        print("No complete weeks found to analyze.")
        return None

    # Print Markdown Table Header
    # Using session index (0=open, 1=next, etc.) might be confusing.
    # Let's use Session Number within week (1=open, 2=next, etc.)
    print("| Session Number in Week | Approx. Session Name | Probability of First Retest |")
    print("| :--------------------- | :------------------- | :-------------------------- |")

    total_probability = 0
    max_session_index = max(retest_counts.keys()) if retest_counts else 0
    session_sequence = ['Asia', 'London', 'NewYork']

    for i in range(1, max_session_index + 1):
        # Convert retest_counts index (0-based from start) to session number (1-based)
        # e.g., retest_counts[1] means retest in the *second* session (index 1)
        count = retest_counts.get(i, 0)
        probability = (count / total_weeks_analyzed) * 100
        total_probability += probability
        # Try to approximate session name
        session_name_index = (i) % len(session_sequence) # Index 1 is Asia, 2 London, 3 NY (0), 4 Asia (1) ...
        approx_session_name = session_sequence[session_name_index]
        day_num = (i // 3) + 1 # Estimate day number (Mon=1)
        day_name = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][min(day_num-1, 6)]
        approx_name = f"{day_name} {approx_session_name}"

        print(f"| Session {i+1:<15} | {approx_name:<20} | {probability:>26.2f}% |")

    no_retest_probability = (no_retest_count / total_weeks_analyzed) * 100
    total_probability += no_retest_probability
    print(f"| No Retest Within Week |                      | {no_retest_probability:>26.2f}% |")
    print(f"| **Total**             |                      | {total_probability:>26.2f}% |") # Should be close to 100%

    return retest_counts, no_retest_count


if __name__ == "__main__":
    print("Starting Weekly Open Retest Analysis...")
    session_df = load_session_summary_data(DATABASE_PATH, TABLE_NAME)

    if session_df is not None:
        results = analyze_weekly_open_retest(session_df)
        if results:
            print("\nAnalysis complete.")
        else:
            print("\nAnalysis could not be completed (e.g., no weeks found).")
    else:
        print("Failed to load data. Exiting analysis.") 