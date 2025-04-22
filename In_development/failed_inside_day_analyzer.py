import pandas as pd
import sqlite3
import os
import numpy as np
from datetime import timedelta
from collections import defaultdict

# --- Configuration ---
DATABASE_PATH = 'crypto_data.db'
DAILY_SUMMARY_TABLE = 'daily_summary'
SESSION_SUMMARY_TABLE = 'session_summary' # Need this for VAH/VAL
TICK_DATA_PATH = 'BTCUSDT_PERP_BINANCE_normalized.txt'
TICK_DATA_COLS = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'BidVolume', 'AskVolume']
HOURLY_TIMEFRAME = '1H' # Timeframe for close confirmation
REVERSAL_LOOKAHEAD_DAYS = 2 # Check for VAL touch on D+1 and D+2
# Session to use for VAH/VAL on Inside Day (can be None for daily VAH/VAL if calculated)
# For simplicity, let's assume we have Daily VAH/VAL in daily_summary or use NY session VAH/VAL
# Using NY session VAH/VAL for now as a proxy
REFERENCE_SESSION_FOR_VA = 'NewYork'
VA_OVERLAP_THRESHOLD = 0.50 # 50%


def load_data(db_path, daily_table, session_table):
    """Loads daily and session summary data."""
    daily_df, session_df = None, None
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return None, None
    try:
        with sqlite3.connect(db_path) as conn:
            if pd.io.sql.has_table(daily_table, conn):
                 print(f"Loading {daily_table} table...")
                 daily_df = pd.read_sql(f'SELECT * FROM {daily_table}', conn, index_col='Date', parse_dates=['Date'])
                 daily_df.index = pd.to_datetime(daily_df.index).date # Ensure index is date object
                 print(f"Loaded {len(daily_df)} rows from {daily_table}.")
                 # Ensure required columns exist
                 req_daily_cols = ['DailyHigh', 'DailyLow']
                 if not all(c in daily_df.columns for c in req_daily_cols):
                     print(f"Error: Missing required columns in {daily_table}: {req_daily_cols}")
                     daily_df = None
            else:
                 print(f"Warning: {daily_table} table not found in DB.")

            if pd.io.sql.has_table(session_table, conn):
                 print(f"Loading {session_table} table...")
                 session_df = pd.read_sql(f'SELECT * FROM {session_table}', conn, parse_dates=['Date', 'SessionStart', 'SessionEnd'])
                 session_df['Date'] = pd.to_datetime(session_df['Date']).dt.date
                 # Ensure required columns exist
                 req_session_cols = ['Date', 'Sessions', 'VAH', 'VAL']
                 if not all(c in session_df.columns for c in req_session_cols):
                     print(f"Error: Missing required columns in {session_table}: {req_session_cols}")
                     session_df = None
                 else:
                    session_df['VAH'] = pd.to_numeric(session_df['VAH'], errors='coerce')
                    session_df['VAL'] = pd.to_numeric(session_df['VAL'], errors='coerce')
                    # Create a multi-index for easier lookup if needed, or filter later
                    # session_df.set_index(['Date', 'Sessions'], inplace=True)
                    print(f"Loaded {len(session_df)} rows from {session_table}.")
            else:
                print(f"Warning: {session_table} table not found in DB.")

        return daily_df, session_df
    except Exception as e:
        print(f"An error occurred loading summary data: {e}")
        return None, None

def load_tick_data(tick_file_path, required_cols):
    """Loads and prepares tick data, setting timestamp as index."""
    if not os.path.exists(tick_file_path):
        print(f"Error: Tick data file not found at {tick_file_path}")
        return None
    try:
        print(f"Loading tick data from {tick_file_path}...")
        df = pd.read_csv(tick_file_path, delimiter=',', header=None, names=required_cols)
        print("Parsing Timestamps...")
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df.dropna(subset=['Timestamp'], inplace=True)
        print("Converting numeric columns...")
        numeric_cols_to_convert = ['Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'BidVolume', 'AskVolume']
        for col in numeric_cols_to_convert:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        print("Setting Timestamp index...")
        df.set_index('Timestamp', inplace=True)
        df.sort_index(inplace=True)
        print(f"Loaded {len(df)} tick data rows.")
        return df
    except Exception as e:
        print(f"An error occurred loading tick data: {e}")
        return None

def resample_to_ohlc(tick_df, timeframe):
    """Resamples tick data to OHLC candles for the given timeframe."""
    print(f"Resampling tick data to {timeframe} OHLC candles...")
    try:
        ohlc_df = tick_df.resample(timeframe, label='left', closed='left').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            #'Volume': 'sum' # Volume not strictly needed for this analysis
        })
        ohlc_df['Open'] = ohlc_df['Open'].fillna(ohlc_df['Close'].shift(1))
        ohlc_df.dropna(subset=['Open', 'High', 'Low', 'Close'], how='all', inplace=True)
        print(f"Resampling complete. {len(ohlc_df)} candles created.")
        return ohlc_df
    except Exception as e:
        print(f"Error during resampling: {e}")
        return None

def calculate_va_overlap_percentage(vah1, val1, vah2, val2):
    """Calculates the overlap percentage between two value areas."""
    if pd.isna(vah1) or pd.isna(val1) or pd.isna(vah2) or pd.isna(val2):
        return 0.0 # No overlap if data is missing

    overlap_low = max(val1, val2)
    overlap_high = min(vah1, vah2)
    overlap_length = max(0, overlap_high - overlap_low)

    total_range_low = min(val1, val2)
    total_range_high = max(vah1, vah2)
    total_range_length = total_range_high - total_range_low

    if total_range_length <= 0:
        # Handle edge cases like zero range or identical VAs
        return 1.0 if overlap_length > 0 else 0.0

    return overlap_length / total_range_length

def get_dynamic_lookback_va(start_date, session_df, ref_session):
    """Finds the lookback period based on >=50% VA overlap and returns avg VAH/VAL."""
    lookback_dates = []
    current_date = start_date

    # Prepare session data for quick lookup
    ref_session_data = session_df[session_df['Sessions'] == ref_session]
    ref_session_data = ref_session_data.set_index('Date')

    while True:
        if current_date not in ref_session_data.index:
            # print(f"Debug: Data for {current_date} not found. Stopping lookback.")
            break # Stop if data for current day is missing

        lookback_dates.append(current_date)

        prev_date = current_date - timedelta(days=1)
        if prev_date not in ref_session_data.index:
            # print(f"Debug: Data for {prev_date} not found. Stopping lookback.")
            break # Stop if previous day data is missing

        # Get VA for current and previous day
        try:
            vah_curr = ref_session_data.loc[current_date, 'VAH']
            val_curr = ref_session_data.loc[current_date, 'VAL']
            vah_prev = ref_session_data.loc[prev_date, 'VAH']
            val_prev = ref_session_data.loc[prev_date, 'VAL']
        except KeyError:
            # print(f"Debug: KeyError accessing VAH/VAL for {current_date} or {prev_date}. Stopping.")
            break # Should not happen if index check passes, but for safety

        overlap = calculate_va_overlap_percentage(vah_curr, val_curr, vah_prev, val_prev)
        # print(f"Debug: Overlap between {current_date} and {prev_date}: {overlap:.2f}")

        if overlap >= VA_OVERLAP_THRESHOLD:
            current_date = prev_date # Continue backward
        else:
            # print(f"Debug: Overlap < {VA_OVERLAP_THRESHOLD}. Stopping lookback.")
            break # Stop lookback

    if not lookback_dates:
        # print(f"Debug: No lookback dates found for start_date {start_date}.")
        return np.nan, np.nan, [] # Return NaNs if no valid period found

    # Calculate average VAH/VAL for the identified lookback period
    lookback_va_data = ref_session_data.loc[lookback_dates]
    avg_vah = lookback_va_data['VAH'].mean()
    avg_val = lookback_va_data['VAL'].mean()

    # print(f"Debug: Lookback for {start_date}: {lookback_dates}. AvgVAH: {avg_vah:.2f}, AvgVAL: {avg_val:.2f}")
    return avg_vah, avg_val, lookback_dates

def analyze_failed_inside_day(daily_df, session_df, tick_df):
    """Analyzes the Failed Inside Day Breakout strategy."""
    if daily_df is None or session_df is None or tick_df is None:
        print("Error: Missing one or more required dataframes.")
        return

    # 1. Identify Inside Days
    daily_df['PrevDayHigh'] = daily_df['DailyHigh'].shift(1)
    daily_df['PrevDayLow'] = daily_df['DailyLow'].shift(1)
    inside_days_initial = daily_df[
        (daily_df['DailyHigh'] < daily_df['PrevDayHigh']) &
        (daily_df['DailyLow'] > daily_df['PrevDayLow'])
    ].copy()

    total_inside_days = len(inside_days_initial)
    print(f"\nFound {total_inside_days} initial Inside Days.")
    if total_inside_days == 0:
        return

    # --- MODIFICATION: Calculate Ref VAH/VAL dynamically ---
    inside_days_with_va = []
    print(f"Calculating dynamic lookback VAH/VAL for {total_inside_days} Inside Days...")
    processed_id_count = 0
    for inside_date, id_row in inside_days_initial.iterrows():
        ref_vah, ref_val, _ = get_dynamic_lookback_va(inside_date, session_df, REFERENCE_SESSION_FOR_VA)
        if not pd.isna(ref_vah) and not pd.isna(ref_val):
            id_row['RefVAH'] = ref_vah
            id_row['RefVAL'] = ref_val
            inside_days_with_va.append(id_row)
        processed_id_count += 1
        if processed_id_count % 5 == 0:
            print(f"  Processed {processed_id_count}/{total_inside_days}...")

    if not inside_days_with_va:
        print("Could not determine valid reference VAH/VAL for any Inside Days.")
        return

    inside_days = pd.DataFrame(inside_days_with_va)
    print(f"Found {len(inside_days)} Inside Days with valid dynamic reference VAH/VAL.")
    # --- End Modification ---

    potential_triggers = 0
    confirmed_triggers = 0
    success_d1 = 0
    success_d2 = 0
    failures = 0

    # Iterate through Inside Days (already filtered for valid RefVA)
    for inside_date, id_row in inside_days.iterrows():
        ref_vah = id_row['RefVAH']
        ref_val = id_row['RefVAL']

        # Get data for Day D+1, D+2
        d1_date = inside_date + timedelta(days=1)
        d2_date = inside_date + timedelta(days=2)

        # *** IMPORTANT: Check if D+1 and D+2 actually exist in daily_df ***
        if d1_date not in daily_df.index or d2_date not in daily_df.index:
            continue # Need data for D+1 and D+2 for checks

        d1_high = daily_df.loc[d1_date, 'DailyHigh']
        d1_low = daily_df.loc[d1_date, 'DailyLow']
        d2_low = daily_df.loc[d2_date, 'DailyLow']

        # 3. Check Initial Breakout & VAH Touch (using dynamic RefVAH)
        if d1_high >= ref_vah:
            potential_triggers += 1

            # 4. Confirm Failed Breakout with Hourly Closes (using dynamic RefVAH)
            try:
                # Convert d1_date back to datetime if needed for tick_df loc
                d1_date_dt = pd.to_datetime(d1_date)
                start_dt = d1_date_dt
                end_dt = d1_date_dt + timedelta(days=1) - timedelta(microseconds=1)

                # Filter ticks for the precise day D+1
                d1_ticks = tick_df.loc[start_dt:end_dt]

                if not d1_ticks.empty:
                    hourly_ohlc_d1 = resample_to_ohlc(d1_ticks, HOURLY_TIMEFRAME)
                    if hourly_ohlc_d1 is not None and not hourly_ohlc_d1.empty:
                        # Check conditions
                        touched_vah = (hourly_ohlc_d1['High'] >= ref_vah).any()
                        closed_above_vah = (hourly_ohlc_d1['Close'] > ref_vah).any()

                        if touched_vah and not closed_above_vah:
                            confirmed_triggers += 1

                            # 5. Check for Decisive Reversal to VAL (using dynamic RefVAL)
                            reversal_achieved = False
                            # Check D+1 Low
                            if d1_low <= ref_val:
                                success_d1 += 1
                                reversal_achieved = True
                            # Check D+2 Low (only if not hit on D+1)
                            elif d2_low <= ref_val:
                                success_d2 += 1
                                reversal_achieved = True

                            if not reversal_achieved:
                                failures += 1
            except KeyError:
                pass # Skip if tick data for the day is missing
            except Exception as e:
                print(f"Error during hourly check for {d1_date}: {e}")
                pass

    # 6. Report Results
    print("\n--- Failed Inside Day Breakout Analysis Results (Dynamic Overlap VA Proxy) ---") # Updated Title
    print(f"Total Inside Days Found: {total_inside_days}")
    print(f"Inside Days with Valid Dynamic Ref VAH/VAL: {len(inside_days)}")
    print(f"Potential Triggers (Day D+1 High >= RefVAH): {potential_triggers}")
    print(f"Confirmed Triggers (Potential Trigger + Hourly Close Condition Met): {confirmed_triggers}")
    print("--------------------------------------------------")
    print(f"Successful Reversals to RefVAL on Day D+1: {success_d1}")
    print(f"Successful Reversals to RefVAL on Day D+2: {success_d2}")
    total_success = success_d1 + success_d2
    print(f"Total Successful Reversals (D+1 or D+2): {total_success}")
    print(f"Total Failures (Triggered but no VAL touch by D+2): {failures}")
    print("--------------------------------------------------")

    if confirmed_triggers > 0:
        success_rate = (total_success / confirmed_triggers) * 100
        failure_rate = (failures / confirmed_triggers) * 100
        print(f"Overall Success Rate: {success_rate:.2f}% ({total_success}/{confirmed_triggers})")
        print(f"Overall Failure Rate: {failure_rate:.2f}% ({failures}/{confirmed_triggers})")
        if total_success > 0:
             prob_d1_success = (success_d1 / total_success) * 100
             prob_d2_success = (success_d2 / total_success) * 100
             print(f"  - Probability Success on D+1 (given success): {prob_d1_success:.2f}% ")
             print(f"  - Probability Success on D+2 (given success): {prob_d2_success:.2f}% ")
    else:
        print("No confirmed triggers found to calculate rates.")


if __name__ == "__main__":
    print("Starting Failed Inside Day Breakout Analysis (Dynamic VA Overlap)...")
    daily_df, session_df = load_data(DATABASE_PATH, DAILY_SUMMARY_TABLE, SESSION_SUMMARY_TABLE)
    tick_df = load_tick_data(TICK_DATA_PATH, TICK_DATA_COLS)

    if daily_df is not None and session_df is not None and tick_df is not None:
        analyze_failed_inside_day(daily_df, session_df, tick_df) # Call the main analysis function
        print("\nAnalysis complete.")
    else:
        print("\nFailed to load necessary data. Exiting analysis.") 