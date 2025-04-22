"""
Derives session‑based key levels (Daily, Weekly, Monday, etc.) and rolling
VWAP values, then saves them into `crypto_data.db`.

This file replaces the old **indicator_calculator.py**.
"""

import pandas as pd
import numpy as np
import sqlite3
import os
import datetime
import config # Import config for any needed params (e.g., session times if relevant later)

# --- Constants ---
DATABASE_PATH = 'crypto_data.db'
SESSION_SUMMARY_TABLE = 'session_summary'
KEY_LEVELS_TABLE = 'btc_key_levels'
VWAP_TABLE = 'session_vwap'
ROLLING_VWAP_WINDOW = 30
# Define VWAP windows
VWAP_WINDOWS = [30, 365]
# Define sessions to EXCLUDE from default indicator calculations
EXCLUDE_SESSIONS = ['Overnight', 'Weekend-Sat', 'Weekend-Sun']  # keep overlap session

# --- Data Loading ---
def load_session_data(db_path, table_name, exclude_sessions=True):
    """Loads session summary data, optionally excluding specific sessions."""
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        return None
    try:
        conn = sqlite3.connect(db_path)
        query_exists = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';"
        if not pd.read_sql(query_exists, conn).shape[0] > 0: 
            print(f"Error: Table '{table_name}' not found."); conn.close(); return None
        
        # Load all columns initially to allow filtering by session name
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, conn, parse_dates=['Date', 'SessionStart', 'SessionEnd']) # Ensure SessionEnd is also parsed if needed later
        conn.close()
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        # Convert relevant columns to numeric
        num_cols = ["SessionOpen", "SessionHigh", "SessionLow", "SessionClose", "SessionVolume"]
        for col in num_cols:
             if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=num_cols, inplace=True)
        
        # --- FIX: Filter out excluded sessions BEFORE sorting/processing --- 
        if exclude_sessions and 'Sessions' in df.columns:
            initial_count = len(df)
            df = df[~df['Sessions'].isin(EXCLUDE_SESSIONS)]
            print(f"Filtered out {initial_count - len(df)} rows for sessions: {EXCLUDE_SESSIONS}")
        # --- END FIX ---
            
        df.sort_values(by=['Date', 'SessionStart'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        print(f"Loaded and validated {len(df)} rows from {table_name} for calculations.")
        return df
    except Exception as e:
        print(f"Error loading session summary data: {e}")
        return None

# --- Indicator Calculations ---

def calculate_rolling_vwap(df, window):
    """Calculates a rolling VWAP for a specific window."""
    print(f"Calculating {window}-session rolling VWAP...")
    vwap_col_name = f'RVWAP_{window}'
    if vwap_col_name in df.columns:
        print(f"{vwap_col_name} already exists, skipping recalculation.")
        return df
    
    if df is None or not all(c in df.columns for c in ['SessionHigh', 'SessionLow', 'SessionClose', 'SessionVolume']):
        print(f"Error: Missing required columns for RVWAP {window} calculation.")
        return df 
    
    # Calculate Typical Price and PV if not already present
    if 'TypicalPrice' not in df.columns:
        df['TypicalPrice'] = (df['SessionHigh'] + df['SessionLow'] + df['SessionClose'] ) / 3
    if 'PV' not in df.columns:
        df['PV'] = df['TypicalPrice'] * df['SessionVolume']
    
    rolling_pv_sum = df['PV'].rolling(window=window, min_periods=window).sum()
    rolling_volume_sum = df['SessionVolume'].rolling(window=window, min_periods=window).sum()
    
    # Calculate Rolling VWAP, handle potential division by zero
    df[vwap_col_name] = np.where(rolling_volume_sum != 0, rolling_pv_sum / rolling_volume_sum, np.nan)
    
    print(f"{vwap_col_name} calculation complete.")
    return df # Return the modified DataFrame

def calculate_key_levels(df):
    """Calculates periodic key levels."""
    print("Calculating Key Levels...")
    if df is None:
        print("Error: Input DataFrame is None.")
        return None

    # Keep the raw UTC column for later joins
    df['SessionStartUTC'] = pd.to_datetime(df['SessionStart'])

    # --- Apply exchange‑offset so that week/day boundaries match TradingView ---
    EX_OFFSET_HRS = getattr(config, 'EXCHANGE_UTC_OFFSET_HRS', 0)  # e.g. 0 for UTC, +8 for UTC+8
    if EX_OFFSET_HRS != 0:
        print(f"Applying exchange offset of {EX_OFFSET_HRS}h to session timestamps for key‑level aggregation …")
    df['AdjSessionStart'] = df['SessionStartUTC'] + pd.Timedelta(hours=EX_OFFSET_HRS)
    # set as index but *retain* the column for downstream merges
    df.set_index('AdjSessionStart', drop=False, inplace=True)

    # --- Create Daily Aggregates --- 
    # Group by date to get daily high/low/open
    daily_agg = df.resample('D').agg(
        DailyOpen=('SessionOpen', 'first'),
        DailyHigh=('SessionHigh', 'max'),
        DailyLow=('SessionLow', 'min')
    ).dropna()
    
    # Calculate Daily Mid
    daily_agg['DailyMid'] = (daily_agg['DailyHigh'] + daily_agg['DailyLow']) / 2

    # Shift to get previous day's values
    daily_agg['PrevDailyHigh'] = daily_agg['DailyHigh'].shift(1)
    daily_agg['PrevDailyLow'] = daily_agg['DailyLow'].shift(1)
    daily_agg['PrevDailyMid'] = daily_agg['DailyMid'].shift(1)

    # --- Create Weekly Aggregates (Starting Monday) --- 
    weekly_agg = df.resample('W-MON').agg(
        WeeklyOpen=('SessionOpen', 'first'),
        WeeklyHigh=('SessionHigh', 'max'),
        WeeklyLow=('SessionLow', 'min') 
    ).dropna()
    weekly_agg['WeeklyMid'] = (weekly_agg['WeeklyHigh'] + weekly_agg['WeeklyLow']) / 2
    weekly_agg['PrevWeekHigh'] = weekly_agg['WeeklyHigh'].shift(1)
    weekly_agg['PrevWeekLow'] = weekly_agg['WeeklyLow'].shift(1)
    weekly_agg['PrevWeekMid'] = weekly_agg['WeeklyMid'].shift(1)

    # --- Monday Specific Levels --- 
    mondays_df = df[df.index.dayofweek == 0] # Monday == 0
    monday_agg = mondays_df.resample('W-MON').agg(
         MondayOpen=('SessionOpen', 'first'), # Technically same as Weekly Open
         MondayHigh=('SessionHigh', 'max'),
         MondayLow=('SessionLow', 'min')
    ).dropna()
    monday_agg['MondayMid'] = (monday_agg['MondayHigh'] + monday_agg['MondayLow']) / 2
    monday_agg['MondayRange'] = monday_agg['MondayHigh'] - monday_agg['MondayLow']
    # We need previous Monday levels, so shift applies here too if needed by spec (spec says Monday H/L/Mid, implying *current* Monday)

    # --- Monthly Aggregates --- 
    monthly_agg = df.resample('MS').agg( # MS for Month Start
        MonthlyOpen=('SessionOpen', 'first'),
        MonthlyHigh=('SessionHigh', 'max'),
        MonthlyLow=('SessionLow', 'min')
    ).dropna()
    monthly_agg['MonthlyMid'] = (monthly_agg['MonthlyHigh'] + monthly_agg['MonthlyLow']) / 2
    monthly_agg['PrevMonthHigh'] = monthly_agg['MonthlyHigh'].shift(1)
    monthly_agg['PrevMonthLow'] = monthly_agg['MonthlyLow'].shift(1)
    monthly_agg['PrevMonthMid'] = monthly_agg['MonthlyMid'].shift(1)

    # --- Quarterly Aggregates --- 
    quarterly_agg = df.resample('QS').agg( # QS for Quarter Start
        QuarterlyOpen=('SessionOpen', 'first'),
        QuarterlyHigh=('SessionHigh', 'max'),
        QuarterlyLow=('SessionLow', 'min')
    ).dropna()
    quarterly_agg['QuarterlyMid'] = (quarterly_agg['QuarterlyHigh'] + quarterly_agg['QuarterlyLow']) / 2
    quarterly_agg['PrevQuarterMid'] = quarterly_agg['QuarterlyMid'].shift(1)

    # --- Yearly Aggregates --- 
    yearly_agg = df.resample('YS').agg( # YS for Year Start
        YearlyOpen=('SessionOpen', 'first'),
        YearlyHigh=('SessionHigh', 'max'),
        YearlyLow=('SessionLow', 'min')
    ).dropna()
    yearly_agg['YearlyMid'] = (yearly_agg['YearlyHigh'] + yearly_agg['YearlyLow']) / 2
    yearly_agg['PrevYearMid'] = yearly_agg['YearlyMid'].shift(1)

    # --- Calculate Previous Session Levels --- 
    # Ensure df is sorted by SessionStart (already done in load_session_data)
    # Need original df with SessionStart index here
    df_for_prev_session = df.copy()
    df_for_prev_session.reset_index(drop=True, inplace=True)
    df_for_prev_session.sort_values(by='SessionStartUTC', inplace=True)
    
    df_for_prev_session['PrevSessionOpen']  = df_for_prev_session['SessionOpen'].shift(1)
    df_for_prev_session['PrevSessionHigh']  = df_for_prev_session['SessionHigh'].shift(1)
    df_for_prev_session['PrevSessionLow']   = df_for_prev_session['SessionLow'].shift(1)
    df_for_prev_session['PrevSessionClose'] = df_for_prev_session['SessionClose'].shift(1)
    df_for_prev_session['PrevSessionMid']   = (
         df_for_prev_session['PrevSessionHigh'] +
         df_for_prev_session['PrevSessionLow']
     ) / 2
    df_for_prev_session['PrevSessionMid'] = (df_for_prev_session['PrevSessionHigh'] + df_for_prev_session['PrevSessionLow']) / 2
    
    # Keep only relevant columns for merge
    prev_session_levels = df_for_prev_session[['SessionStartUTC',
                                               'PrevSessionOpen', 'PrevSessionHigh',
                                               'PrevSessionLow', 'PrevSessionClose',
                                               'PrevSessionMid']].copy()
    # --- End Previous Session Calc ---

    # --- Merge levels back using pd.merge --- 
    df_out = df[['Date', 'SessionOpen', 'SessionStartUTC']].copy()
    df_out['SessionDate'] = pd.to_datetime(df_out.index.date) 
    df_out.reset_index(inplace=True) # Keep SessionStart as a column

    # Ensure aggregate indices are datetime objects for merging keys if needed
    daily_agg.index = pd.to_datetime(daily_agg.index)
    weekly_agg.index = pd.to_datetime(weekly_agg.index)
    monday_agg.index = pd.to_datetime(monday_agg.index)
    monthly_agg.index = pd.to_datetime(monthly_agg.index)
    quarterly_agg.index = pd.to_datetime(quarterly_agg.index)
    yearly_agg.index = pd.to_datetime(yearly_agg.index)
    
    # --- Merge Daily --- 
    df_out['MergeDate'] = pd.to_datetime(df_out['SessionDate'])
    df_out = pd.merge(df_out, daily_agg[['DailyOpen', 'PrevDailyMid']], 
                      left_on='MergeDate', right_index=True, how='left')
                      
    # --- Merge Weekly/Monday --- 
    df_out['WeekStartDate'] = df_out['MergeDate'].apply(lambda x: x - pd.to_timedelta(x.weekday(), unit='d'))
    df_out = pd.merge(df_out, weekly_agg[['WeeklyOpen', 'PrevWeekHigh', 'PrevWeekLow', 'PrevWeekMid']],
                      left_on='WeekStartDate', right_index=True, how='left')
    df_out = pd.merge(df_out, monday_agg[['MondayHigh', 'MondayLow', 'MondayMid', 'MondayRange']],
                      left_on='WeekStartDate', right_index=True, how='left') # Monday data also indexed by week start

    # --- Merge Monthly --- 
    df_out['MonthStartDate'] = df_out['MergeDate'].apply(lambda x: x.replace(day=1))
    df_out = pd.merge(df_out, monthly_agg[['MonthlyOpen', 'PrevMonthHigh', 'PrevMonthLow', 'PrevMonthMid']],
                      left_on='MonthStartDate', right_index=True, how='left')

    # --- Merge Quarterly --- 
    df_out['QuarterStartDate'] = df_out['MergeDate'].apply(lambda x: pd.Timestamp(x).to_period('Q').start_time)
    df_out = pd.merge(df_out, quarterly_agg[['QuarterlyOpen', 'PrevQuarterMid']],
                      left_on='QuarterStartDate', right_index=True, how='left')
                      
    # --- Merge Yearly --- 
    df_out['YearStartDate'] = df_out['MergeDate'].apply(lambda x: x.replace(month=1, day=1))
    df_out = pd.merge(df_out, yearly_agg[['YearlyOpen', 'PrevYearMid']],
                      left_on='YearStartDate', right_index=True, how='left')

    # --- Merge Previous Session Levels --- 
    # Ensure SessionStart is datetime for merge
    prev_session_levels['SessionStartUTC'] = pd.to_datetime(prev_session_levels['SessionStartUTC'])
    df_out = pd.merge(df_out, prev_session_levels,
                      on='SessionStartUTC', how='left')
    # --- End Merge --- 

    # --- Cleanup and Final Selection ---
    # Drop temporary merge keys
    df_out.drop(columns=['MergeDate', 'WeekStartDate', 'MonthStartDate', 'QuarterStartDate', 'YearStartDate'], inplace=True, errors='ignore') # Add errors='ignore'
    
    # Select and order final columns (Add new PrevSession* columns)
    final_cols = ['SessionStart', 'SessionDate', 'SessionOpen', 
                  # Previous Session Levels
                  'PrevSessionOpen', 'PrevSessionHigh', 'PrevSessionLow', 'PrevSessionClose', 'PrevSessionMid',
                  # Period Levels
                  'DailyOpen', 'PrevDailyMid', 
                  'MondayHigh', 'MondayLow', 'MondayMid', 'MondayRange', 
                  'WeeklyOpen', 'PrevWeekHigh', 'PrevWeekLow', 'PrevWeekMid', 
                  'MonthlyOpen', 'PrevMonthHigh', 'PrevMonthLow', 'PrevMonthMid',
                  'QuarterlyOpen', 'PrevQuarterMid', 
                  'YearlyOpen', 'PrevYearMid']
    
    key_levels_df = df_out[[col for col in final_cols if col in df_out.columns]].copy()    # SessionStartUTC already present; nothing to rename
    print(f"Key Levels calculation complete. {len(key_levels_df)} rows generated.")
    return key_levels_df

# --- Database Saving ---
def save_to_db(df, table_name, db_path):
    """Saves a DataFrame to a specified table in the SQLite database, replacing if exists."""
    if df is None or df.empty:
        print(f"DataFrame for table {table_name} is empty or None. Skipping save.")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            print(f"Saving {len(df)} rows to table '{table_name}'...")
            df_save = df.copy()
            
            # --- Explicit Type Conversion and Debugging --- 
            print(f"  Data types BEFORE conversion for {table_name}:\n{df_save.dtypes}")
            cols_to_convert = []
            for col in df_save.columns:
                col_type = df_save[col].dtype
                is_date_object_col = False
                if col_type == object:
                    try:
                        is_date_object_col = any(isinstance(x, datetime.date) and not isinstance(x, datetime.datetime) for x in df_save[col].dropna())
                    except TypeError:
                        pass 
                
                # Identify columns needing conversion (Simplified check)
                needs_conversion = False
                if pd.api.types.is_datetime64_any_dtype(col_type):
                    needs_conversion = True
                elif isinstance(col_type, pd.PeriodDtype):
                    needs_conversion = True
                elif is_date_object_col:
                    needs_conversion = True
                    
                if needs_conversion:
                    cols_to_convert.append(col)
            
            if cols_to_convert:
                print(f"  Explicitly converting columns to string: {cols_to_convert}")
                for col in cols_to_convert:
                    df_save[col] = df_save[col].astype(str)
            
            print(f"  Data types AFTER conversion for {table_name}:\n{df_save.dtypes}")
            # --- End Conversion and Debugging --- 
                
            df_save.to_sql(table_name, conn, if_exists='replace', index=False)
            print(f"Table '{table_name}' saved successfully.")
    except Exception as e:
        print(f"Error saving table '{table_name}' to database: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Indicator Calculations (Excluding Overnight/Weekend by default)...")
    session_df_filtered = load_session_data(DATABASE_PATH, SESSION_SUMMARY_TABLE, exclude_sessions=True)
    
    if session_df_filtered is not None:
        # --- FIX: Reinstate loop for calculating VWAPs --- 
        vwap_base_df = session_df_filtered.copy() # Start with filtered data
        vwap_cols_to_keep = ['Date', 'SessionStart'] # Base columns
        calculated_vwap_cols = [] 
        
        for window in VWAP_WINDOWS: # Loop through [30, 365]
            vwap_base_df = calculate_rolling_vwap(vwap_base_df, window) # Pass window
            if vwap_base_df is not None and f'RVWAP_{window}' in vwap_base_df.columns:
                 vwap_cols_to_keep.append(f'RVWAP_{window}')
                 calculated_vwap_cols.append(f'RVWAP_{window}')
        # --- END FIX ---
                 
        if vwap_base_df is not None:
            final_vwap_df = vwap_base_df[vwap_cols_to_keep].copy()
            if calculated_vwap_cols: final_vwap_df.dropna(subset=calculated_vwap_cols, how='all', inplace=True)
            if 'SessionStart' in final_vwap_df.columns: final_vwap_df.rename(columns={'SessionStart':'SessionStartUTC'}, inplace=True)
            save_to_db(final_vwap_df, VWAP_TABLE, DATABASE_PATH)
        else:
            print("VWAP calculation failed.")
        
        key_levels_results_df = calculate_key_levels(session_df_filtered.copy()) 
        save_to_db(key_levels_results_df, KEY_LEVELS_TABLE, DATABASE_PATH)
        
        print("\nIndicator calculations and database saving complete.")
    else:
        print("\nFailed to load filtered session data. Indicator calculations aborted.") 