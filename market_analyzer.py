import pandas as pd
import sys
import sqlite3 # Added for database operations
import datetime # Needed for time objects
import json # To store list as string in SQLite
import os # Import os to check for DB file existence
import numpy as np # Needed for calculations
import config # Import parameters from config.py
import string # Needed for TPO letters
import argparse  # <--- add after existing imports (ensure unique)

# Session Definitions now in config.py

def get_active_sessions(timestamp: pd.Timestamp):
    """Return list of session names active at *timestamp* (UTC).

    Logic is entirely driven by *config.SESSIONS* so that new windows
    (e.g. LDN_NY_Overlap) require no code change here.
    """
    if not isinstance(timestamp, pd.Timestamp):
        return []

    t   = timestamp.time()
    wd  = timestamp.dayofweek  # 0=Mon

    # Weekend special cases first
    if wd == 5:
        return ['Weekend-Sat']
    if wd == 6:
        return ['Weekend-Sun']

    active = []
    for name, (start, end) in config.SESSIONS.items():
        if start <= end:  # same‑day session
            if start <= t < end:
                active.append(name)
        else:  # overnight session (e.g., 21:00‑00:00)
            if t >= start or t < end:
                active.append(name)

    return active

def load_and_preprocess_data(filename):
    """
    Loads the normalized tick data, assigns column names, converts types,
    and adds a Date column for 24-hour session grouping.

    Args:
        filename (str): The path to the normalized CSV data file.

    Returns:
        pandas.DataFrame: The preprocessed data in a DataFrame, or None if an error occurs.
    """
    print(f"Loading data from {filename}...")
    
    column_names = [
        'Timestamp', 'Open', 'High', 'Low', 'Close', 
        'Volume', 'Trades', 'BidVolume', 'AskVolume'
    ]
    
    numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'BidVolume', 'AskVolume']

    try:
        # Read the CSV file
        df = pd.read_csv(
            filename, 
            header=None, # No header row in the file
            names=column_names,
            low_memory=False # Recommended for large files with mixed types initially
        )
        print("Initial load complete. Starting preprocessing...")

        # 1. Convert Timestamp column to datetime objects
        print("Converting Timestamp column...")
        # Use explicit format for speed: 'YYYY-MM-DD HH:MM:SS'
        df['Timestamp'] = pd.to_datetime(
            df['Timestamp'],
            format='%Y-%m-%d %H:%M:%S',  # adjust if milliseconds exist
            errors='coerce'
        )
        # Drop rows where timestamp conversion failed
        df.dropna(subset=['Timestamp'], inplace=True)
        print(f"Timestamp conversion done. Data shape: {df.shape}")

        # 2. Convert numeric columns
        print("Converting numeric columns...")
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        # Optionally, handle rows where numeric conversion failed (e.g., drop or fill)
        # For now, let's report if any NaNs were introduced
        if df[numeric_cols].isnull().any().any():
            print("Warning: NaNs introduced during numeric conversion. Consider handling.")
            # df.dropna(subset=numeric_cols, inplace=True) # Example: Drop rows with NaNs
        print(f"Numeric conversion done. Data shape: {df.shape}")

        # 3. Add a 'Date' column for 24hr session grouping
        print("Adding Date column...")
        df['Date'] = df['Timestamp'].dt.date
        print(f"Date column added. Data shape: {df.shape}")
        
        # 4. Set Timestamp as index (optional, but often useful)
        # print("Setting Timestamp as index...")
        # df.set_index('Timestamp', inplace=True)
        # print(f"Index set. Data shape: {df.shape}")
        
        print("Preprocessing complete.")
        return df

    except FileNotFoundError:
        print(f"Error: Input file '{filename}' not found.")
        return None
    except Exception as e:
        print(f"An error occurred during data loading or preprocessing: {e}")
        return None

def calculate_delta(df):
    """
    Calculates the Delta (AskVolume - BidVolume) for each row.

    Args:
        df (pandas.DataFrame): The preprocessed DataFrame with AskVolume and BidVolume columns.

    Returns:
        pandas.DataFrame: The DataFrame with an added 'Delta' column.
    """
    print("\nCalculating Delta...")
    if 'AskVolume' in df.columns and 'BidVolume' in df.columns:
        df['Delta'] = df['AskVolume'] - df['BidVolume']
        print(f"Delta column added. Data shape: {df.shape}")
    else:
        print("Error: 'AskVolume' or 'BidVolume' columns not found. Cannot calculate Delta.")
    return df

def calculate_daily_summary(df):
    """
    Calculates daily OHLC, Volume, and cumulative Delta from tick data.

    Args:
        df (pandas.DataFrame): Preprocessed DataFrame with Timestamp, Date, 
                               OHLC, Volume, and Delta columns.

    Returns:
        pandas.DataFrame: A DataFrame indexed by Date with daily summary data, 
                          or None if required columns are missing.
    """
    print("\nCalculating Daily Summary (OHLC, Volume, Delta)...")
    required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Delta']
    if not all(col in df.columns for col in required_cols):
        print(f"Error: Missing one or more required columns for daily summary: {required_cols}")
        return None
    
    if not pd.api.types.is_datetime64_any_dtype(df.index):
         # Ensure Timestamp is the index for correct first/last aggregation
        if 'Timestamp' in df.columns:
             print("Setting Timestamp as index for aggregation...")
             df = df.set_index('Timestamp')
        else:
            print("Error: Timestamp column missing or not set as index for daily aggregation.")
            return None
            
    try:
        daily_summary = df.groupby('Date').agg(
            DailyOpen=pd.NamedAgg(column='Open', aggfunc='first'),
            DailyHigh=pd.NamedAgg(column='High', aggfunc='max'),
            DailyLow=pd.NamedAgg(column='Low', aggfunc='min'),
            DailyClose=pd.NamedAgg(column='Close', aggfunc='last'),
            DailyVolume=pd.NamedAgg(column='Volume', aggfunc='sum'),
            DailyDelta=pd.NamedAgg(column='Delta', aggfunc='sum')
        )
        print(f"Daily summary calculated. Shape: {daily_summary.shape}")
        return daily_summary
    except Exception as e:
        print(f"An error occurred during daily summary calculation: {e}")
        return None

def calculate_session_summary(df):
    """
    Calculates session OHLC, Volume, and cumulative Delta from tick data.
    Handles overlapping sessions by potentially double-counting ticks in summaries.

    Args:
        df (pandas.DataFrame): Preprocessed tick DataFrame with Timestamp, Date, Sessions,
                               OHLC, Volume, and Delta columns.

    Returns:
        pandas.DataFrame: A DataFrame indexed by Date and Session with session summary data,
                          or None if required columns are missing.
    """
    print("\nCalculating Session Summary (OHLC, Volume, Delta)...")
    required_cols = ['Timestamp', 'Date', 'Sessions', 'Open', 'High', 'Low', 'Close', 'Volume', 'Delta']
    if not all(col in df.columns for col in required_cols):
        print(f"Error: Missing one or more required columns for session summary: {required_cols}")
        return None
    
    # Ensure data is sorted by Timestamp for correct first/last aggregation
    df_sorted = df.sort_values('Timestamp')

    # Explode the 'Sessions' list into separate rows
    # Ticks outside defined sessions or with invalid session data will be dropped here
    df_exploded = df_sorted.explode('Sessions').dropna(subset=['Sessions'])
    
    if df_exploded.empty:
        print("Warning: No data points found within defined sessions after exploding.")
        return None
        
    print(f"Exploded data for session calculation. Shape: {df_exploded.shape}")

    try:
        # Group by Date and Session Name
        session_grouped = df_exploded.groupby(['Date', 'Sessions'])
        
        # Aggregate
        session_summary = session_grouped.agg(
            SessionStart=pd.NamedAgg(column='Timestamp', aggfunc='min'),
            SessionEnd=pd.NamedAgg(column='Timestamp', aggfunc='max'),
            SessionOpen=pd.NamedAgg(column='Open', aggfunc='first'),
            SessionHigh=pd.NamedAgg(column='High', aggfunc='max'),
            SessionLow=pd.NamedAgg(column='Low', aggfunc='min'),
            SessionClose=pd.NamedAgg(column='Close', aggfunc='last'),
            SessionVolume=pd.NamedAgg(column='Volume', aggfunc='sum'),
            SessionDelta=pd.NamedAgg(column='Delta', aggfunc='sum'),
            SessionTicks=pd.NamedAgg(column='Timestamp', aggfunc='size') # Count ticks per session
        )
        print(f"Session summary calculated. Shape: {session_summary.shape}")
        return session_summary
    except Exception as e:
        print(f"An error occurred during session summary calculation: {e}")
        return None

def calculate_atr(daily_df, period=config.ATR_PERIOD if hasattr(config, 'ATR_PERIOD') else 14):
    """
    Calculates the Average True Range (ATR) for the daily data.

    Args:
        daily_df (pandas.DataFrame): DataFrame with daily High, Low, Close data.
                                    It must have DailyHigh, DailyLow, DailyClose columns.
        period (int): The period for the ATR calculation (default 14).

    Returns:
        pandas.DataFrame: The input DataFrame with an added 'ATR' column, 
                          or None if required columns are missing.
    """
    print(f"\nCalculating ATR with period {period}...")
    required_cols = ['DailyHigh', 'DailyLow', 'DailyClose']
    if not all(col in daily_df.columns for col in required_cols):
        print(f"Error: Missing one or more required columns for ATR calculation: {required_cols}")
        return None

    # Calculate True Range (TR)
    high_low = daily_df['DailyHigh'] - daily_df['DailyLow']
    high_close_prev = abs(daily_df['DailyHigh'] - daily_df['DailyClose'].shift(1))
    low_close_prev = abs(daily_df['DailyLow'] - daily_df['DailyClose'].shift(1))
    
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    
    # Calculate ATR using Exponential Moving Average (EMA)
    # Note: Using adjust=False for compatibility with common TA library results
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    
    daily_df['ATR'] = atr
    print(f"ATR column added. Shape: {daily_df.shape}")
    # print(daily_df[['DailyHigh', 'DailyLow', 'DailyClose', 'ATR']].tail()) # Optional: print tail for verification
    return daily_df

def calculate_session_vpoc(tick_df, session_df, date_limit=None):
    """
    Calculates the Volume Point of Control (VPOC) for each session.
    Optionally limits calculation to a specific number of initial dates for testing.

    Args:
        tick_df (pandas.DataFrame): DataFrame with tick data.
        session_df (pandas.DataFrame): DataFrame with session summary data.
        date_limit (int, optional): Limit calculation to the first N unique dates. Defaults to None (process all).

    Returns:
        pandas.DataFrame: The session_df DataFrame with 'SessionVPOC' column.
    """
    print(f"\nCalculating Session VPOC... (Date limit: {date_limit})")
    if tick_df is None or session_df is None:
        print("Error: Input DataFrames for VPOC calculation are missing.")
        return None
        
    required_tick_cols = ['Timestamp', 'Date', 'Sessions', 'Close', 'Volume']
    if not all(col in tick_df.columns for col in required_tick_cols):
        print(f"Error: Missing one or more required columns in tick_df for VPOC: {required_tick_cols}")
        return None

    vpocs = {}
    
    # Determine dates to process
    all_dates = session_df.index.get_level_values('Date').unique().sort_values()
    if date_limit is not None and date_limit > 0:
        dates_to_process = all_dates[:date_limit]
        print(f"Limiting VPOC calculation to first {len(dates_to_process)} dates: {dates_to_process.tolist()}")
        # Filter session_df to only include rows for these dates for iteration
        sessions_to_process_df = session_df[session_df.index.get_level_values('Date').isin(dates_to_process)]
    else:
        dates_to_process = all_dates
        sessions_to_process_df = session_df # Process all sessions
        
    total_sessions_to_process = len(sessions_to_process_df)
    processed_count = 0
    print(f"Processing VPOC for {total_sessions_to_process} session instances.")

    # Iterate through the potentially filtered sessions
    for (date, session_name), session_data in sessions_to_process_df.iterrows():
        # Filter tick data for the specific date and session name
        # Handle cases where Sessions column might be stored as list or JSON string initially
        is_list = isinstance(tick_df['Sessions'].iloc[0], list) 
        if is_list:
            mask = (tick_df['Date'] == date) & (tick_df['Sessions'].apply(lambda x: session_name in x))
        else: # Assume JSON string if not list
             mask = (tick_df['Date'] == date) & (tick_df['Sessions'].str.contains(f'"{session_name}"'))
             
        session_ticks = tick_df[mask]

        vpoc = None
        if not session_ticks.empty:
            volume_at_price = session_ticks.groupby(session_ticks['Close'].round(1))['Volume'].sum()
            if not volume_at_price.empty and volume_at_price.max() > 0:
                 vpoc = volume_at_price.idxmax()
            else:
                 vpoc = None
        else:
             vpoc = None
            
        vpocs[(date, session_name)] = vpoc
        
        processed_count += 1
        if processed_count % 100 == 0 or processed_count == total_sessions_to_process:
             print(f"Processed {processed_count}/{total_sessions_to_process} sessions for VPOC...")
            
    print(f"Finished processing sessions for VPOC.")

    # Create a Series from the calculated vpocs dictionary
    new_vpocs_series = pd.Series(vpocs)
    new_vpocs_series.index.names = ['Date', 'Sessions'] # Ensure index names match for update

    # Update the SessionVPOC column in the original session_df
    if 'SessionVPOC' not in session_df.columns:
        # If column doesn't exist, create it from the new Series
        session_df['SessionVPOC'] = new_vpocs_series
        print("SessionVPOC column created.")
    else:
        # If column exists, update it with non-null values from the new Series
        print("Updating existing SessionVPOC column...")
        session_df['SessionVPOC'].update(new_vpocs_series)
        # Explicitly overwrite NaNs from the limited calc if needed (update might not overwrite existing None/NaN with a calculated value)
        # session_df.loc[new_vpocs_series.index, 'SessionVPOC'] = new_vpocs_series # Alternative overwrite
    
    # Convert VPOC column to numeric, coercing errors (like None) to NaN
    session_df['SessionVPOC'] = pd.to_numeric(session_df['SessionVPOC'], errors='coerce')

    # Final check message
    non_null_vpoc_count = session_df['SessionVPOC'].notnull().sum()
    if non_null_vpoc_count > 0:
         print(f"SessionVPOC column updated/added. {non_null_vpoc_count} non-null values found. Example type: {session_df['SessionVPOC'].dtype}")
    else:
         print("SessionVPOC column added/updated, but all processed values are null.")
    return session_df

def calculate_tpo_metrics(tick_df, session_df, tpo_period_minutes, price_step, value_area_percent, ib_periods, date_limit=None):
    """
    Calculates TPO metrics (POC, VA, IB, Poor High/Low, Single Prints) for each session.
    """
    print(f"\nCalculating TPO Metrics... (Period: {tpo_period_minutes}min, Step: {price_step}, VA: {value_area_percent*100}%, IB Periods: {ib_periods}, Date Limit: {date_limit})")
    
    tpo_results = {}
    tpo_period_str = f'{tpo_period_minutes}min'
    tpo_letters = list(string.ascii_uppercase) + list(string.ascii_lowercase) 

    # Determine dates/sessions to process
    all_dates = session_df.index.get_level_values('Date').unique().sort_values()
    if date_limit is not None and date_limit > 0:
        dates_to_process = all_dates[:date_limit]
        print(f"Limiting TPO calculation to first {len(dates_to_process)} dates: {dates_to_process.tolist()}")
        sessions_to_process_df = session_df[session_df.index.get_level_values('Date').isin(dates_to_process)]
    else:
        sessions_to_process_df = session_df
        
    total_sessions_to_process = len(sessions_to_process_df)
    processed_count = 0
    print(f"Processing TPO for {total_sessions_to_process} session instances.")

    debug_first_session = True # Flag for debug prints

    for (date, session_name), session_data in sessions_to_process_df.iterrows():
        session_start = session_data['SessionStart']
        session_end = session_data['SessionEnd']

        # Filter ticks for the session
        session_ticks = tick_df[(tick_df['Timestamp'] >= session_start) & (tick_df['Timestamp'] <= session_end)].copy()

        if session_ticks.empty:
            tpo_results[(date, session_name)] = {'TPO_POC': np.nan, 'VAH': np.nan, 'VAL': np.nan, 'IB_High': np.nan, 'IB_Low': np.nan, 'PoorHigh': False, 'PoorHighPrice': np.nan, 'PoorLow': False, 'PoorLowPrice': np.nan, 'SinglePrints': False}
            processed_count += 1
            continue
            
        session_ticks.set_index('Timestamp', inplace=True)

        # Assign TPO letters based on resampling
        # Create time bins
        time_bins = pd.date_range(start=session_start.floor(tpo_period_str), end=session_end.ceil(tpo_period_str), freq=tpo_period_str)
        if len(time_bins) < 2: # Need at least one full period 
             tpo_results[(date, session_name)] = {'TPO_POC': np.nan, 'VAH': np.nan, 'VAL': np.nan, 'IB_High': np.nan, 'IB_Low': np.nan, 'PoorHigh': False, 'PoorHighPrice': np.nan, 'PoorLow': False, 'PoorLowPrice': np.nan, 'SinglePrints': False}
             processed_count += 1
             continue
             
        # Ensure we don't exceed available letters
        num_periods = len(time_bins) -1
        if num_periods > len(tpo_letters):
             print(f"Warning: Session {date} {session_name} has more TPO periods ({num_periods}) than available letters ({len(tpo_letters)}). Skipping.")
             tpo_results[(date, session_name)] = {'TPO_POC': np.nan, 'VAH': np.nan, 'VAL': np.nan, 'IB_High': np.nan, 'IB_Low': np.nan, 'PoorHigh': False, 'PoorHighPrice': np.nan, 'PoorLow': False, 'PoorLowPrice': np.nan, 'SinglePrints': False}
             processed_count += 1
             continue
             
        period_labels = {time_bins[i]: tpo_letters[i] for i in range(num_periods)}
        # Assign TPO letter based on which bin the timestamp falls into
        session_ticks['TPO_Letter'] = pd.cut(session_ticks.index, bins=time_bins, labels=list(period_labels.values()), right=False, include_lowest=True)
        session_ticks.dropna(subset=['TPO_Letter'], inplace=True) # Drop ticks outside defined periods

        if session_ticks.empty:
             tpo_results[(date, session_name)] = {'TPO_POC': np.nan, 'VAH': np.nan, 'VAL': np.nan, 'IB_High': np.nan, 'IB_Low': np.nan, 'PoorHigh': False, 'PoorHighPrice': np.nan, 'PoorLow': False, 'PoorLowPrice': np.nan, 'SinglePrints': False}
             processed_count += 1
             continue

        # Build profile
        min_price = session_ticks['Low'].min()
        max_price = session_ticks['High'].max()
        # Create discrete price levels
        price_levels = np.arange(np.floor(min_price / price_step) * price_step, 
                               np.ceil(max_price / price_step) * price_step + price_step, 
                               price_step)
        price_levels = np.round(price_levels, decimals=8) # Avoid precision issues

        tpo_counts = pd.Series(0, index=price_levels)
        letters_at_price = {level: set() for level in price_levels} # Store letters per level

        for letter, period_ticks in session_ticks.groupby('TPO_Letter', observed=False):
            period_low = period_ticks['Low'].min()
            period_high = period_ticks['High'].max()
            low_idx = np.floor(period_low / price_step) * price_step
            high_idx = np.ceil(period_high / price_step) * price_step
            touched_levels = price_levels[(price_levels >= np.round(low_idx, 8)) & (price_levels < np.round(high_idx, 8))] # Use < high_idx
            
            if len(touched_levels) > 0:
                 tpo_counts.loc[touched_levels] += 1
                 for level in touched_levels:
                     letters_at_price[level].add(letter)

        # --- Calculate Metrics --- 
        tpo_poc_level = np.nan
        vah_level = np.nan
        val_level = np.nan
        ib_high_level = np.nan
        ib_low_level = np.nan
        is_poor_high = False
        poor_high_price = np.nan
        is_poor_low = False
        poor_low_price = np.nan
        has_single_prints = False
        session_high_price = session_data['SessionHigh'] # Get actual session high/low
        session_low_price = session_data['SessionLow']

        valid_tpo_counts = tpo_counts[tpo_counts > 0]
        if not valid_tpo_counts.empty:
            # Calculate TPO POC
            tpo_poc_level = valid_tpo_counts.idxmax() 

            # Calculate Value Area
            total_tpos = valid_tpo_counts.sum()
            target_va_tpos = int(total_tpos * value_area_percent)
            
            # Start from POC and expand outwards
            poc_index_loc = valid_tpo_counts.index.get_loc(tpo_poc_level)
            va_indices = {poc_index_loc}
            current_va_tpos = valid_tpo_counts.iloc[poc_index_loc]
            
            upper_idx, lower_idx = poc_index_loc + 1, poc_index_loc - 1
            while current_va_tpos < target_va_tpos and (lower_idx >= 0 or upper_idx < len(valid_tpo_counts)):
                add_upper = upper_idx < len(valid_tpo_counts)
                add_lower = lower_idx >= 0

                tpos_upper = valid_tpo_counts.iloc[upper_idx] if add_upper else -1
                tpos_lower = valid_tpo_counts.iloc[lower_idx] if add_lower else -1
                
                # Add level with more TPOs first, or upper if equal
                if tpos_upper >= tpos_lower and add_upper:
                     va_indices.add(upper_idx)
                     current_va_tpos += tpos_upper
                     upper_idx += 1
                elif tpos_lower > tpos_upper and add_lower:
                     va_indices.add(lower_idx)
                     current_va_tpos += tpos_lower
                     lower_idx -= 1
                elif add_lower: # Only lower is left
                     va_indices.add(lower_idx)
                     current_va_tpos += tpos_lower
                     lower_idx -= 1
                elif add_upper: # Only upper is left
                     va_indices.add(upper_idx)
                     current_va_tpos += tpos_upper
                     upper_idx += 1
                else:
                     break # Should not happen
            
            if va_indices:
                 va_level_indices = sorted(list(va_indices))
                 val_level = valid_tpo_counts.index[va_level_indices[0]]
                 vah_level = valid_tpo_counts.index[va_level_indices[-1]]

            # Calculate Initial Balance
            ib_letters = tpo_letters[:ib_periods]
            ib_ticks = session_ticks[session_ticks['TPO_Letter'].isin(ib_letters)]
            if not ib_ticks.empty:
                ib_high_level = ib_ticks['High'].max()
                ib_low_level = ib_ticks['Low'].min()

            # Poor High / Poor Low
            session_high_level = np.round(np.floor(session_high_price / price_step) * price_step, 8)
            session_low_level = np.round(np.floor(session_low_price / price_step) * price_step, 8)
            
            # Check if the level exists in our profile index
            if session_high_level in letters_at_price:
                 if len(letters_at_price[session_high_level]) >= config.POOR_EXTREME_TPO_THRESHOLD:
                      is_poor_high = True
                      poor_high_price = session_high_price
            if session_low_level in letters_at_price:
                  if len(letters_at_price[session_low_level]) >= config.POOR_EXTREME_TPO_THRESHOLD:
                      is_poor_low = True
                      poor_low_price = session_low_price
                      
            # ── START SP DETECT  (v2 – threshold OR span, tolerant of tiny gaps) ──
            """
            Flags the session as having single prints if

              • at least THRESH consecutive single‑TPO price levels **OR**
              • the total span of all single‑print levels ≥ MIN_SPAN_USD.

            A "consecutive" run allows a one‑tick gap (to forgive missing rungs).
            Threshold knobs live in config.py when present; otherwise defaults
            below are used.
            """

            THRESH       = getattr(config, "SINGLE_PRINT_THRESHOLD", 3)
            MIN_SPAN_USD = getattr(config, "SINGLE_PRINT_MIN_SPAN", 20.0)

            single_print_levels = valid_tpo_counts[valid_tpo_counts == 1].index.to_numpy()
            has_single_prints = False

            if single_print_levels.size:
                 # (a) longest almost‑consecutive run (allow one‑tick gaps)
                 diffs      = np.diff(single_print_levels)
                 tol        = price_step * 0.51
                 consec     = 1
                 max_consec = 1
                 for d in diffs:
                      if d <= price_step + tol:   # 0 or 1 tick gap
                           consec += 1
                      else:
                           max_consec = max(max_consec, consec)
                           consec = 1
                 max_consec = max(max_consec, consec)

                 # (b) span of entire single‑print region
                 span_usd = single_print_levels[-1] - single_print_levels[0] if single_print_levels.size > 1 else 0.0

                 if (max_consec >= THRESH) or (span_usd >= MIN_SPAN_USD):
                      has_single_prints = True
            # ── END SP DETECT ───────────────────────────────────────────

            # Determine high/low price of single‑print region if detected
            sp_high_price = np.nan
            sp_low_price  = np.nan
            if has_single_prints:
                sp_high_price = float(single_print_levels.max()) if single_print_levels.size else np.nan
                sp_low_price  = float(single_print_levels.min()) if single_print_levels.size else np.nan

        tpo_results[(date, session_name)] = {
            'TPO_POC': tpo_poc_level,
            'VAH': vah_level,
            'VAL': val_level,
            'IB_High': ib_high_level,
            'IB_Low': ib_low_level,
            'PoorHigh': is_poor_high,
            'PoorHighPrice': poor_high_price,
            'PoorLow': is_poor_low,
            'PoorLowPrice': poor_low_price,
            'SinglePrints': has_single_prints,
            'SP_High': sp_high_price,
            'SP_Low': sp_low_price
        }
        
        debug_first_session = False # Disable debug prints after first session
        processed_count += 1
        if processed_count % 10 == 0 or processed_count == total_sessions_to_process:
            print(f"Processed {processed_count}/{total_sessions_to_process} sessions for TPO...")

    print("Finished processing TPO metrics.")

    # Update session_df
    tpo_df = pd.DataFrame.from_dict(tpo_results, orient='index')
    tpo_df.index.names = ['Date', 'Sessions']
    
    # Update existing columns or add new ones
    for col in tpo_df.columns:
         session_df[col] = tpo_df[col] 
         # Convert numeric/bool types appropriately 
         if col in ['PoorHigh', 'PoorLow', 'SinglePrints']:
              session_df[col] = session_df[col].astype(bool) # Ensure boolean type
         else: # Assume numeric for others
             session_df[col] = pd.to_numeric(session_df[col], errors='coerce')

    print("TPO columns updated/added.")
    return session_df

def save_to_database(tick_df, daily_df, session_df, db_filename):
    """
    Saves all three DataFrames to SQLite, handling new TPO & ASR columns.
    """
    print(f"\nSaving data to database: {db_filename}...")
    try:
        with sqlite3.connect(db_filename) as conn:
            # --- Save tick data --- 
            if tick_df is not None:
                print(f"Saving tick_data table ({len(tick_df)} rows)...")
                tick_df_to_save = tick_df.copy()
                if pd.api.types.is_datetime64_any_dtype(tick_df_to_save.index):
                    tick_df_to_save.reset_index(inplace=True)
                
                if 'Timestamp' in tick_df_to_save.columns and pd.api.types.is_datetime64_any_dtype(tick_df_to_save['Timestamp']):
                     tick_df_to_save['Timestamp'] = tick_df_to_save['Timestamp'].astype(str)
                
                if 'Date' in tick_df_to_save.columns and not pd.api.types.is_string_dtype(tick_df_to_save['Date']) and not pd.api.types.is_object_dtype(tick_df_to_save['Date']):
                    tick_df_to_save['Date'] = tick_df_to_save['Date'].astype(str)

                if 'Sessions' in tick_df_to_save.columns:
                    if tick_df_to_save['Sessions'].apply(lambda x: isinstance(x, list)).any():
                         print("Converting Sessions list to JSON string...")
                         tick_df_to_save['Sessions'] = tick_df_to_save['Sessions'].apply(json.dumps)
                    # else: # Removed unnecessary print
                    #      print("Sessions column already seems to be stored as string.")

                tick_df_to_save.to_sql('tick_data', conn, if_exists='replace', index=False)
                print("tick_data table saved.")
            else:
                print("Tick data DataFrame is None, skipping save.")
                
            # --- Save daily summary data --- 
            if daily_df is not None:
                print(f"Saving daily_summary table ({len(daily_df)} rows)...")
                daily_df_to_save = daily_df.copy()
                daily_df_to_save.reset_index(inplace=True)
                if 'Date' in daily_df_to_save.columns and not pd.api.types.is_string_dtype(daily_df_to_save['Date']) and not pd.api.types.is_object_dtype(daily_df_to_save['Date']):
                    daily_df_to_save['Date'] = daily_df_to_save['Date'].astype(str)
                
                daily_df_to_save.to_sql('daily_summary', conn, if_exists='replace', index=False)
                print("daily_summary table saved.")
            else:
                print("Daily summary DataFrame is None, skipping save.")
            
            # --- Save session summary data --- 
            if session_df is not None:
                print(f"Saving session_summary table ({len(session_df)} rows)...")
                session_df_to_save = session_df.copy()
                session_df_to_save.reset_index(inplace=True)
                if 'Date' in session_df_to_save.columns and not pd.api.types.is_string_dtype(session_df_to_save['Date']) and not pd.api.types.is_object_dtype(session_df_to_save['Date']):
                     session_df_to_save['Date'] = session_df_to_save['Date'].astype(str)
                if 'SessionStart' in session_df_to_save.columns:
                     session_df_to_save['SessionStart'] = session_df_to_save['SessionStart'].astype(str)
                if 'SessionEnd' in session_df_to_save.columns:
                     session_df_to_save['SessionEnd'] = session_df_to_save['SessionEnd'].astype(str)
                     
                # Convert boolean columns to integer (0/1) for SQLite compatibility
                bool_cols = ['PoorHigh', 'PoorLow', 'SinglePrints']
                for col in bool_cols:
                     if col in session_df_to_save.columns:
                          session_df_to_save[col] = session_df_to_save[col].astype(int)
                     
                session_df_to_save.to_sql('session_summary', conn, if_exists='replace', index=False)
                print("session_summary table saved.")
            else:
                print("Session summary DataFrame is None, skipping save.")
                
        print("Data successfully saved to database.")
        
    except sqlite3.Error as e:
        print(f"Database error occurred: {e}")
    except Exception as e:
        print(f"An error occurred during database save: {e}")

if __name__ == "__main__":
    # Use parameters from config file
    TPO_PERIOD_MINUTES = config.TPO_PERIOD_MINUTES
    PRICE_STEP = config.PRICE_STEP
    VALUE_AREA_PERCENT = config.VALUE_AREA_PERCENT
    INITIAL_BALANCE_PERIODS = config.INITIAL_BALANCE_PERIODS
    # Use ATR_PERIOD from config if defined, else default to 14
    ATR_PERIOD = config.ATR_PERIOD if hasattr(config, 'ATR_PERIOD') else 14
    
    VPOC_DATE_LIMIT = None 
    TPO_DATE_LIMIT = None # Limit TPO calc to first 10 days for debugging Single Prints - DISABLED FOR FULL RUN

    DB_FILE = "crypto_data.db"
    INPUT_FILE = "BTCUSDT_PERP_BINANCE_normalized.txt"
    
    # --- Argument parsing ---
    parser = argparse.ArgumentParser(description="Process BTCUSDT tick data and rebuild database if requested", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="Ignore existing crypto_data.db and rebuild tables from input file")
    parser.add_argument("--file", default=INPUT_FILE, help="Path to the normalised tick file to process")
    args = parser.parse_args()

    # Apply CLI overrides
    INPUT_FILE = args.file

    # --- Option to load from DB (unless --rebuild supplied) --- 
    LOAD_FROM_DB = os.path.exists(DB_FILE) and (not args.rebuild)
    if LOAD_FROM_DB:
         print(f"Database file found ({DB_FILE}). Attempting to load data...")
    else:
         print(f"Database file ({DB_FILE}) not found. Processing from file...")

    data_df = None
    daily_df = None
    session_df = None

    if LOAD_FROM_DB:
        print(f"Attempting to load data from database: {DB_FILE}...")
        try:
            with sqlite3.connect(DB_FILE) as conn:
                # Load tick_data
                if pd.io.sql.has_table('tick_data', conn):
                     print("Loading tick_data table...")
                     # Load Date as string initially
                     data_df = pd.read_sql('SELECT * FROM tick_data', conn, parse_dates=['Timestamp'])
                     # **** Convert Date column to date objects AFTER loading ****
                     if 'Date' in data_df.columns:
                          print("Converting loaded Date column to date objects...")
                          data_df['Date'] = pd.to_datetime(data_df['Date']).dt.date
                     
                     # Convert Sessions back from JSON string to list
                     if 'Sessions' in data_df.columns:
                          try:
                              data_df['Sessions'] = data_df['Sessions'].apply(json.loads)
                              print("Converted Sessions column from JSON string.")
                          except (json.JSONDecodeError, TypeError) as e:
                              print(f"Warning: Could not parse Sessions column as JSON: {e}")
                     print(f"Loaded {len(data_df)} rows from tick_data.")
                else:
                     print("tick_data table not found in DB.")
                     
                # Load daily_summary
                if pd.io.sql.has_table('daily_summary', conn):
                     print("Loading daily_summary table...")
                     daily_df = pd.read_sql('SELECT * FROM daily_summary', conn, index_col='Date', parse_dates=['Date'])
                     daily_df.index = pd.to_datetime(daily_df.index).date
                     print(f"Loaded {len(daily_df)} rows from daily_summary.")
                else:
                     print("daily_summary table not found in DB.")
                     
                # Load session_summary
                if pd.io.sql.has_table('session_summary', conn):
                     print("Loading session_summary table...")
                     session_df = pd.read_sql('SELECT * FROM session_summary', conn, parse_dates=['Date', 'SessionStart', 'SessionEnd'])
                     session_df['Date'] = pd.to_datetime(session_df['Date']).dt.date 
                     if 'Date' in session_df.columns and 'Sessions' in session_df.columns:
                          session_df = session_df.set_index(['Date', 'Sessions'])
                     print(f"Loaded {len(session_df)} rows from session_summary.")
                     # *** ADDED: Print columns after loading ***
                     print(f"Columns loaded from session_summary: {session_df.columns.tolist()}") 
                else:
                     print("session_summary table not found in DB.")
                     
        except sqlite3.Error as e:
            print(f"Database error during load: {e}")
            data_df, daily_df, session_df = None, None, None # Ensure reset on error
        except Exception as e:
             print(f"An error occurred during database load: {e}")
             data_df, daily_df, session_df = None, None, None # Ensure reset on error
             
    # If loading any part from DB failed or was disabled, process from file
    if data_df is None:
        print("\nProcessing data from file...")
        data_df = load_and_preprocess_data(INPUT_FILE)
        
        if data_df is not None:
            data_df = calculate_delta(data_df)
            # Add Sessions Column
            print("\nAdding Sessions column...")
            if 'Timestamp' in data_df.columns:
                data_df['Sessions'] = data_df['Timestamp'].apply(get_active_sessions)
                print(f"Sessions column added. Data shape: {data_df.shape}")
            else:
                print("Error: Timestamp column not found, cannot add Sessions.")
                data_df = None 

    # --- Calculate Summaries & Metrics (only if tick data is available) --- 
    if data_df is not None:
        # Calculate Daily Summary (if not loaded)
        if daily_df is None: 
            print("\nRecalculating Daily Summary...")
            daily_df_input = data_df.copy()
            if not isinstance(daily_df_input.index, pd.DatetimeIndex) and 'Timestamp' in daily_df_input.columns:
                try: daily_df_input = daily_df_input.set_index('Timestamp')
                except KeyError: daily_df_input = None
            elif not isinstance(daily_df_input.index, pd.DatetimeIndex): daily_df_input = None
            
            if daily_df_input is not None and isinstance(daily_df_input.index, pd.DatetimeIndex):
                daily_df = calculate_daily_summary(daily_df_input)
            else: daily_df = None
        
        # Calculate Session Summary (if not loaded)
        if session_df is None:
            print("\nCalculating Session Summary...")
            session_df = calculate_session_summary(data_df)
        
        # Calculate ATR (if daily data available and needed)
        if daily_df is not None:
             if 'ATR' not in daily_df.columns:
                 print("\nCalculating ATR...")
                 daily_df = calculate_atr(daily_df, period=ATR_PERIOD)
             # else: print("ATR column already exists.") # Optional
        else:
             print("\nDaily summary data not available, cannot calculate ATR.")

        # Calculate VPOC (if session data available and needed)
        if session_df is not None:
            run_vpoc_calc = False
            if 'SessionVPOC' not in session_df.columns:
                 print("\nSessionVPOC column missing. Calculating VPOC...") 
                 run_vpoc_calc = True
            elif session_df['SessionVPOC'].isnull().any():
                 print(f"\nFound NaNs in existing SessionVPOC. Calculating VPOC for all dates...")
                 run_vpoc_calc = True
            else:
                 print("\nSessionVPOC column exists and contains no NaNs. Skipping calculation.")

            if run_vpoc_calc:
                 session_df = calculate_session_vpoc(data_df, session_df, date_limit=None)
        else:
             print("\nSession summary data not available, cannot calculate VPOC.")

        # Calculate TPO Metrics (if tick and session data available)
        if session_df is not None:
            tpo_cols = ['TPO_POC', 'VAH', 'VAL', 'IB_High', 'IB_Low', 'PoorHigh', 'PoorLow', 'SinglePrints']
            run_tpo_calc = False # Resetting default behavior
            # ** Force calculation if limit is set **
            if TPO_DATE_LIMIT is not None:
                 print(f"\nForcing TPO recalculation for first {TPO_DATE_LIMIT} days (debug run)...")
                 run_tpo_calc = True
            elif not all(col in session_df.columns for col in tpo_cols):
                 print("\nOne or more TPO columns missing. Calculating TPO...") 
                 run_tpo_calc = True
            elif session_df[tpo_cols].isnull().any().any(): 
                 print(f"\nFound NaNs in existing TPO columns. Calculating TPO for all dates...")
                 run_tpo_calc = True 
            else:
                 print("\nTPO columns exist and contain no NaNs. Skipping calculation.")

            if run_tpo_calc:
                 session_df = calculate_tpo_metrics(data_df, session_df, 
                                                   TPO_PERIOD_MINUTES, PRICE_STEP, 
                                                   VALUE_AREA_PERCENT, INITIAL_BALANCE_PERIODS, 
                                                   date_limit=TPO_DATE_LIMIT)
            else: # Restore else block
                 print("\nSkipping TPO calculation based on existing data.") 
        else:
             print("\nSession summary data not available, cannot calculate TPO metrics.")

        # --- Calculate Session ASR (if session data is available) --- 
        if session_df is not None:
            # Calculate only if column doesn't exist
            if 'SessionASR' not in session_df.columns:
                 print("\nCalculating Session ASR...")
                 session_df['SessionASR'] = (session_df['SessionHigh'] - session_df['SessionLow']).round(1)
                 print("SessionASR column added.")
            # else: print("SessionASR column already exists.") # Optional
        else:
             print("\nSession summary data not available, cannot calculate SessionASR.")

    else:
         print("\nTick data not available, cannot calculate summaries.")

    # --- Print Results & Save --- 
    print("\n--- Final DataFrames --- ")
    if data_df is not None:
        print("\nTick Data Sample:")
        print(data_df.head())
    else: print("\nTick data not available.")
        
    if daily_df is not None:
        print("\nDaily Summary Sample:")
        print(daily_df.head())
    else: print("\nDaily summary not available.")
    
    if session_df is not None:
        print("\nSession Summary Sample:")
        print(session_df.head())
        print("\nSession Summary Info:")
        session_df.info()
    else: print("\nSession summary not available.")

    # Save results to database if we processed from file or recalculated VPOC
    # Determine if saving is needed
    save_needed = False
    if not LOAD_FROM_DB and data_df is not None: # Always save if processed from file
        save_needed = True
        print("\nSaving all data to database (processed from file)...")
    elif LOAD_FROM_DB and session_df is not None and 'SessionVPOC' in session_df.columns: 
        # Potentially check if VPOC was *just* calculated vs loaded, but for simplicity, save if loaded and VPOC exists
        # This assumes if loaded, we might have recalculated VPOC if it was missing.
        # A more robust check would involve flags, but this is simpler for now.
        save_needed = True # Re-save session_summary if loaded from DB & VPOC exists
        print("\nUpdating session_summary in database (potentially with new VPOC)...")
        # Set other dfs to None to only save session_summary
        data_df = None 
        daily_df = None
    elif LOAD_FROM_DB and daily_df is not None and 'ATR' in daily_df.columns: 
         # Handle case where only ATR was recalculated on loaded data
         save_needed = True
         print("\nUpdating daily_summary in database (potentially with new ATR)...")
         data_df = None
         session_df = None

    if save_needed:
        save_to_database(data_df, daily_df, session_df, DB_FILE)
    elif not LOAD_FROM_DB:
         print("\nSkipping database save as processing failed.")
            
    # Final exit condition
    if data_df is None and not LOAD_FROM_DB:
         print("\nExiting due to failure in data loading or processing from file.")
         sys.exit(1)
    elif data_df is None and session_df is None and daily_df is None and LOAD_FROM_DB:
         print("\nExiting due to failure loading data from database.")
         sys.exit(1)