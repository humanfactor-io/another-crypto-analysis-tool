import streamlit as st
import pandas as pd
import sqlite3
import os
import numpy as np
import datetime
import config # Import parameters like TPO_PERIOD_MINUTES etc.
import mplfinance as mpf # For visualization
import matplotlib.pyplot as plt # For formatting price axis
import matplotlib.ticker as mticker # For formatting price axis
import matplotlib.dates as mdates # Needed for axvspan with dates
# import matplotlib.dates as mdates # Needed for plotting lines on time axis
# import streamlit.components.v1 as components # For rendering HTML

# --- Configuration & Constants ---
DATABASE_PATH = 'crypto_data.db'
SESSION_SUMMARY_TABLE = 'session_summary'
TICK_DATA_PATH = 'BTCUSDT_PERP_BINANCE_normalized.txt'
TICK_DATA_COLS = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'BidVolume', 'AskVolume']
# CHART_CANDLE_TIMEFRAME = '15T' # Removed hardcoded timeframe
KEY_LEVELS_TABLE = 'btc_key_levels' # Add table name
VWAP_TABLE = 'session_vwap' # Define table name

# Define available timeframes for dropdown
TIMEFRAME_OPTIONS = {
    # Minutes
    "5 Minutes": "5min",
    "15 Minutes": "15min",
    "30 Minutes": "30min",
    "45 Minutes": "45min",
    # Hours
    "1 Hour": "1H",
    "4 Hours": "4H",
    "6 Hours": "6H",
    "12 Hours": "12H",
    # Days (Using 'D' for daily)
    "1 Day": "D",
    # Weeks (Using 'W' or 'W-MON' for weekly starting Monday)
    # "1 Week": "W-MON", # Weekly might be too coarse for session overlays
    # Months (Using 'M' or 'MS' for month start)
    # "1 Month": "MS", # Monthly might be too sparse
}

# --- Data Loading Functions (with Caching) ---
@st.cache_data # Cache the loaded summary data
def load_summary_data(db_path, table_name):
    """Loads session summary data from SQLite."""
    if not os.path.exists(db_path):
        st.error(f"Database file not found: {db_path}")
        return None
    try:
        conn = sqlite3.connect(db_path)
        # Convert bools back if needed for display
        df = pd.read_sql(f'SELECT * FROM {table_name}', conn,
                         parse_dates=['Date', 'SessionStart', 'SessionEnd'])
        conn.close()
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        # Ensure boolean columns are bool type for display logic
        for col in ['PoorHigh', 'PoorLow', 'SinglePrints']:
            if col in df.columns:
                 try: 
                     df[col] = df[col].astype(bool)
                 except Exception:
                     df[col] = False 
        print(f"Loaded {len(df)} rows from {table_name}.")
        return df
    except Exception as e:
        st.error(f"Error loading session summary data: {e}")
        return None

@st.cache_data # Cache key levels too
def load_key_levels_data(db_path, table_name):
    """Loads key levels data from SQLite."""
    if not os.path.exists(db_path):
        st.error(f"Database file not found: {db_path}")
        return None
    try:
        conn = sqlite3.connect(db_path)
        # Check if table exists first
        query = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';"
        table_exists = pd.read_sql(query, conn).shape[0] > 0
        if not table_exists:
             st.warning(f"Table '{table_name}' not found in database. Run indicator_calculator.py?")
             conn.close()
             return None
             
        # Load data, parsing relevant date/time columns if they exist
        # SessionStartUTC was saved as string, SessionDate needs parsing back
        df = pd.read_sql(f'SELECT * FROM {table_name}', conn, parse_dates=['SessionStartUTC'])
        df['SessionDate'] = pd.to_datetime(df['SessionDate']).dt.date
        conn.close()
        print(f"Loaded {len(df)} rows from {table_name}.")
        return df
    except Exception as e:
        st.error(f"Error loading key levels data: {e}")
        return None

@st.cache_data # Cache VWAP data
def load_session_vwap_data(db_path, table_name):
    """Loads session VWAP data from SQLite."""
    if not os.path.exists(db_path):
        st.error(f"Database file not found: {db_path}")
        return None
    try:
        conn = sqlite3.connect(db_path)
        query = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';"
        table_exists = pd.read_sql(query, conn).shape[0] > 0
        if not table_exists:
             st.warning(f"Table '{table_name}' not found in database. Run indicator_calculator.py?")
             conn.close()
             return None
             
        df = pd.read_sql(f'SELECT * FROM {table_name}', conn, parse_dates=['SessionStartUTC'])

        # --- FIX: Check for RVWAP column names --- 
        # Construct list of required column names based on config
        vwap_windows_list = config.VWAP_WINDOWS if hasattr(config, 'VWAP_WINDOWS') else [30]
        required_vwap_cols = [f'RVWAP_{w}' for w in vwap_windows_list] # Corrected list comprehension
        if not all(col in df.columns for col in required_vwap_cols):
            st.error(f"Missing one or more expected VWAP columns ({required_vwap_cols}) in {table_name}")
            conn.close()
            return None
        # --- END FIX ---
            
        conn.close()
        # --- FIX: Rename SessionStart to Timestamp AFTER parsing --- 
        df.rename(columns={'SessionStartUTC': 'Timestamp'}, inplace=True)
        # --- END FIX ---
        df.set_index('Timestamp', inplace=True)
        print(f"Loaded {len(df)} rows from {table_name}.")
        return df
    except Exception as e:
        st.error(f"Error loading session VWAP data: {e}")
        return None

def load_range_tick_data(tick_file_path, required_cols, start_date, end_date):
    """Loads tick data for a date range efficiently."""
    if not os.path.exists(tick_file_path):
        st.error(f"Tick data file not found: {tick_file_path}")
        return None

    all_ticks_list = []
    # We no longer pass a strict dtype_map because some raw files include a header row
    # ("Timestamp,Open,High,…").  Enforcing float dtype on 'Open' etc. would raise
    # "could not convert string to float: 'Open'".  Instead we let pandas infer dtypes
    # then coerce numerics manually after filtering the date range.
    
    st.info(f"Loading tick data from {start_date} to {end_date}...")
    # Iterate through each day in the range
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        st.info(f"  Reading data for {date_str}...") # Progress update
        try:
            # Using chunking for potentially large daily files
            chunk_list_day = []
            for chunk in pd.read_csv(tick_file_path, delimiter=',', header=0, names=required_cols,
                                     skipinitialspace=True, on_bad_lines='skip', chunksize=500000):
                # More robust date filtering
                chunk['TimestampParsed'] = pd.to_datetime(chunk['Timestamp'], errors='coerce')
                chunk_filtered = chunk[chunk['TimestampParsed'].dt.date == current_date]
                if not chunk_filtered.empty:
                    chunk_list_day.append(chunk_filtered.drop(columns=['TimestampParsed'])) # Drop temp column

            if chunk_list_day:
                day_df = pd.concat(chunk_list_day, ignore_index=True)
                all_ticks_list.append(day_df)
            # else: # Optional: Add warning if a day has no data
                # st.warning(f"No tick data found for {date_str}.")

        except FileNotFoundError:
            st.error(f"Tick data file not found: {tick_file_path}") # Should be caught earlier ideally
            return None
        except Exception as e:
            st.error(f"Error loading tick data chunk for {date_str}: {e}")
            # Optionally decide whether to continue or fail completely
            # return None
        current_date += datetime.timedelta(days=1)

    if not all_ticks_list:
        st.error(f"No tick data loaded for the selected range {start_date} to {end_date}.")
        return None

    # Concatenate all daily dataframes
    df = pd.concat(all_ticks_list, ignore_index=True)
    st.success(f"Concatenated data for {len(all_ticks_list)} days.")

    # Final processing
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df.dropna(subset=['Timestamp'], inplace=True)
    numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'BidVolume', 'AskVolume']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df.set_index('Timestamp', inplace=True)
    df.sort_index(inplace=True)
    st.success(f"Loaded and processed {len(df)} tick data rows for the range.")
    return df

def resample_ticks_for_chart(session_ticks, timeframe):
    """Resamples session ticks to OHLC for mplfinance chart."""
    if session_ticks is None or session_ticks.empty:
        return None
    try:
        ohlc = session_ticks.resample(timeframe, label='left', closed='left').agg(
            Open=('Open', 'first'),
            High=('High', 'max'),
            Low=('Low', 'min'),
            Close=('Close', 'last'),
            Volume=('Volume', 'sum') # Keep volume for potential use
        ).dropna(subset=['Open', 'High', 'Low', 'Close'], how='all')
        # Forward fill open from previous close only if Open is NaN but Close is not
        mask = ohlc['Open'].isna() & ohlc['Close'].shift(1).notna()
        ohlc.loc[mask, 'Open'] = ohlc['Close'].shift(1)
        # Drop any remaining rows where OHLC are all NaN
        ohlc.dropna(subset=['Open', 'High', 'Low', 'Close'], how='all', inplace=True)
        return ohlc
    except Exception as e:
        st.error(f"Error resampling ticks for chart: {e}")
        return None

# --- Calculation Functions ---
# @st.cache_data # Commented out - Function no longer called directly here
def get_weekly_rotation_status(summary_df, key_levels_df):
    """Calculates which weeks had a full Monday H/L rotation (Tue-Fri)
       and returns the Monday High/Low for those weeks.
    """
    st.info("Calculating weekly rotation status and levels...") # Update message
    if summary_df is None or key_levels_df is None:
        st.warning("Missing summary or key level data for rotation calculation.")
        return None

    # --- Merge required data --- 
    level_cols = ['SessionStartUTC', 'MondayHigh', 'MondayLow']
    summary_cols = ['SessionStart', 'SessionHigh', 'SessionLow']
    df_levels = key_levels_df[level_cols].copy()
    df_levels.rename(columns={'SessionStartUTC': 'SessionStart'}, inplace=True)
    df_summary = summary_df[summary_cols].copy()
    df_levels['SessionStart'] = pd.to_datetime(df_levels['SessionStart'])
    df_summary['SessionStart'] = pd.to_datetime(df_summary['SessionStart'])
    df_merged = pd.merge(df_summary, df_levels, on='SessionStart', how='inner')
    if df_merged.empty: return None
    for col in ['SessionHigh', 'SessionLow', 'MondayHigh', 'MondayLow']:
        df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')
    df_merged.dropna(subset=['MondayHigh', 'MondayLow', 'SessionHigh', 'SessionLow'], inplace=True)
    if df_merged.empty: return None
    # --- End Merge --- 

    # ... Add Week and DayOfWeek ...
    df_merged['WeekOfYearMon'] = df_merged['SessionStart'].dt.strftime('%Y-%W')
    df_merged['DayOfWeek'] = df_merged['SessionStart'].dt.dayofweek

    # Filter for Tue-Fri
    df_analysis = df_merged[df_merged['DayOfWeek'].isin([1, 2, 3, 4])].copy()
    if df_analysis.empty: return None 

    # Flag touches
    df_analysis['TouchedMondayHigh'] = df_analysis['SessionHigh'] >= df_analysis['MondayHigh']
    df_analysis['TouchedMondayLow'] = df_analysis['SessionLow'] <= df_analysis['MondayLow']

    # Group and check if both were touched
    weekly_touches = df_analysis.groupby('WeekOfYearMon')[['TouchedMondayHigh', 'TouchedMondayLow']].any()
    weekly_touches['FullRotation'] = weekly_touches['TouchedMondayHigh'] & weekly_touches['TouchedMondayLow']
    
    # Get the weeks where full rotation occurred
    rotation_weeks = weekly_touches[weekly_touches['FullRotation']].index
    
    # --- FIX: Get Monday H/L for rotation weeks --- 
    # Get the first MondayHigh/Low value for each week from the original merged df
    # (since it's constant for the week)
    monday_levels_per_week = df_merged.groupby('WeekOfYearMon').agg(
        MondayHigh = pd.NamedAgg(column='MondayHigh', aggfunc='first'),
        MondayLow = pd.NamedAgg(column='MondayLow', aggfunc='first')
    )
    
    # Filter for only the weeks that had rotation
    rotation_week_levels = monday_levels_per_week.loc[rotation_weeks]
    # --- END FIX ---
    
    st.success("Weekly rotation levels calculated.") # Update message
    return rotation_week_levels # Return DataFrame with MonH/L for rotation weeks

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("BTCUSDT.P Session Data & Structure Viewer") # Updated title

# --- Load Data --- 
summary_df = load_summary_data(DATABASE_PATH, SESSION_SUMMARY_TABLE)
key_levels_df = load_key_levels_data(DATABASE_PATH, KEY_LEVELS_TABLE)
vwap_df = load_session_vwap_data(DATABASE_PATH, VWAP_TABLE) # Load VWAP data

# Calculate rotation status
# rotation_status = get_weekly_rotation_status(summary_df, key_levels_df) # Commented out

# --- Display Summary Table (Optional) --- 
if summary_df is not None:
    st.header("Session Summary Data")
    show_summary = st.checkbox("Show Summary Table", value=False, key='show_summary')
    if show_summary:
        with st.container(height=400):
             st.dataframe(summary_df.style.format({col: '{:.1f}' 
                for col in summary_df.select_dtypes(include=np.number).columns if col not in ['SessionTicks'] 
            }, na_rep="None"))
        
# --- Display Key Levels Table (Conditional) ---
st.header("Key Levels Data")
period_level_cols = ['SessionStartUTC', 'SessionDate', 'SessionOpen', 'DailyOpen', 'PrevDailyMid',
                     'MondayHigh', 'MondayLow', 'MondayMid', 'MondayRange', 
                     'WeeklyOpen', 'PrevWeekHigh', 'PrevWeekLow', 'PrevWeekMid', 
                     'MonthlyOpen', 'PrevMonthHigh', 'PrevMonthLow', 'PrevMonthMid',
                     'QuarterlyOpen', 'PrevQuarterMid', 'YearlyOpen', 'PrevYearMid']
prev_session_level_cols = ['SessionStartUTC', 'SessionDate', 'SessionOpen', 
                           'PrevSessionOpen', 'PrevSessionHigh', 'PrevSessionLow', 'PrevSessionClose', 'PrevSessionMid']

level_view_choice = st.radio(
    "Select Key Level View:", 
    ("Period Levels", "Previous Session Levels"), 
    horizontal=True,
    key='level_view'
)

if key_levels_df is not None:
    if level_view_choice == "Period Levels":
        cols_to_show = [col for col in period_level_cols if col in key_levels_df.columns]
    else:
        cols_to_show = [col for col in prev_session_level_cols if col in key_levels_df.columns]
    
    if cols_to_show:
         df_to_display = key_levels_df[cols_to_show]
         with st.container(height=400):
              st.dataframe(df_to_display.style.format({col: '{:.1f}' for col in df_to_display.select_dtypes(include=np.number).columns}, na_rep="None"))
    else:
         st.warning(f"Selected columns for view '{level_view_choice}' not found in data.")
else:
     st.info("Key Levels data not loaded. Run indicator_calculator.py to generate it.")

# --- Display Price/Volume Indicators Table (Optional) ---
st.markdown("---") # Separator before VWAP table
st.header("Price and Volume Indicators")
show_indicators = st.checkbox("Show Price/Volume Indicators Table", value=False, key='show_indicators')
if show_indicators:
    if vwap_df is not None:
        vwap_cols_to_select = [col for col in vwap_df.columns if col.startswith('RVWAP')]
        if vwap_cols_to_select:
            df_vwap_display = vwap_df[vwap_cols_to_select].reset_index()
            if 'Timestamp' in df_vwap_display.columns:
                cols = df_vwap_display.columns.tolist()
                cols.insert(0, cols.pop(cols.index('Timestamp')))
                df_vwap_display = df_vwap_display[cols]
            
            with st.container(height=400):
                 st.dataframe(df_vwap_display.style.format({ 
                    col: '{:.1f}'
                    for col in df_vwap_display.select_dtypes(include=np.number).columns
                }, na_rep="None"))
        else:
             st.info("No RVWAP columns found in the loaded VWAP data.")
    else:
         st.info("VWAP data not loaded. Run indicator_calculator.py to generate it.")
# FIX: Add separator AFTER the VWAP table section
st.markdown("---") 

# --- Chart Section --- 
st.header("Chart Visualization")
# Check if summary_df is loaded for date range calculation
if summary_df is not None:
    min_date = summary_df['Date'].min()
    max_date = summary_df['Date'].max()
    
    # --- Chart UI Controls --- 
    col1, col2, col3, col4 = st.columns([2, 2, 2, 3]) # Adjust column widths
    with col1:
        start_date = st.date_input("Start Date:", value=max_date - datetime.timedelta(days=4), min_value=min_date, max_value=max_date)
    with col2:
        end_date = st.date_input("End Date:", value=max_date, min_value=min_date, max_value=max_date)
    with col3:
        selected_tf_label = st.selectbox("Timeframe:", options=list(TIMEFRAME_OPTIONS.keys()), index=1)
        selected_tf_freq = TIMEFRAME_OPTIONS[selected_tf_label]
    with col4:
        # --- VWAP Selection --- 
        st.markdown("**Overlays:**")
        show_vwap30 = st.checkbox("VWAP 30", value=True)
        show_vwap365 = st.checkbox("VWAP 365", value=False)
        # ----------------------
        
    if st.button("Generate Chart"):
        if start_date > end_date:
            st.error("Error: End date must fall after start date.")
        else:
            range_ticks_df = load_range_tick_data(TICK_DATA_PATH, TICK_DATA_COLS, start_date, end_date)
            if range_ticks_df is not None:
                ohlc_data = resample_ticks_for_chart(range_ticks_df, selected_tf_freq)
                if ohlc_data is not None and not ohlc_data.empty:
                    st.success("OHLC data prepared.")
                    
                    # --- Prepare VWAP data & addplots --- 
                    addplot_list = []
                    if vwap_df is not None:
                        # Reindex VWAP data to match OHLC index, ffill
                        vwap_plot_data = vwap_df.reindex(ohlc_data.index, method='ffill')
                        
                        # --- FIX: Calculate VWAP 30 col name separately --- 
                        vwap_window_30 = config.ROLLING_VWAP_WINDOW if hasattr(config, 'ROLLING_VWAP_WINDOW') else 30
                        vwap_col_name_30 = f'RVWAP_{vwap_window_30}'
                        # --- END FIX --- 
                        
                        if show_vwap30:
                            if vwap_col_name_30 in vwap_plot_data.columns and not vwap_plot_data[vwap_col_name_30].isnull().all():
                                addplot_list.append(mpf.make_addplot(vwap_plot_data[vwap_col_name_30], color='purple', width=1.0, panel=0, ylabel='VWAP'))
                            else: st.warning("No RVWAP 30 data available for this range/timeframe.")
                        
                        # FIX: Use RVWAP_365
                        if show_vwap365:
                            vwap_col_name_365 = 'RVWAP_365' 
                            if vwap_col_name_365 in vwap_plot_data.columns and not vwap_plot_data[vwap_col_name_365].isnull().all():
                                addplot_list.append(mpf.make_addplot(vwap_plot_data[vwap_col_name_365], color='blue', width=1.2, linestyle='--', panel=0))
                            else: st.warning("No RVWAP 365 data available for this range/timeframe.")
                    # ---------------------------------------
                    
                    # ... (Filter sessions_in_range) ...
                    sessions_in_range = summary_df[(summary_df['Date'] >= start_date) & (summary_df['Date'] <= end_date)].sort_values(by=['Date', 'SessionStart']).copy()
                    sessions_in_range.dropna(subset=['TPO_POC', 'VAH', 'VAL'], inplace=True) 

                    st.info(f"Plotting {len(ohlc_data)} candles...")
                    try:
                        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', inherit=True)
                        s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')
                        
                        chart_title = f"Chart: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({selected_tf_label})"
                        if addplot_list: chart_title += " & VWAP(s)"
                        
                        fig, axlist = mpf.plot(ohlc_data,
                                               type='candle',
                                               style=s,
                                               title=chart_title,
                                               ylabel='Price',
                                               volume=True, 
                                               addplot=addplot_list if addplot_list else None, 
                                               returnfig=True,
                                               figsize=(15, 8))

                        ax = axlist[0]
                        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.1f'))

                        # --- Plot Rotation Week Mon H/L Lines --- 
                        # if rotation_status is not None and not rotation_status.empty:
                        #     st.info(f"Highlighting Monday levels for {len(rotation_status)} rotation week(s).")
                        #     ohlc_index = ohlc_data.index # Get the index from plotted data
                        #     # Iterate through the rotation weeks data (Index=WeekStr, Columns=MondayHigh, MondayLow)
                        #     for week_str, levels in rotation_status.iterrows():
                        #         mon_high = levels['MondayHigh']
                        #         mon_low = levels['MondayLow']
                        #         
                        #         # Find start/end dates for this week
                        #         try:
                        #             year, week_num = map(int, week_str.split('-'))
                        #             week_start_date = datetime.datetime.strptime(f'{year}-{week_num}-1', "%Y-%W-%w")
                        #             week_end_date = week_start_date + datetime.timedelta(days=7)
                        #         except ValueError: continue # Skip if week string format is wrong
                        #         
                        #         # Find integer index locations for the week span
                        #         try:
                        #             start_loc = ohlc_index.searchsorted(week_start_date)
                        #             end_loc_insert = ohlc_index.searchsorted(week_end_date) 
                        #             end_loc = end_loc_insert - 1
                        #             if end_loc_insert < len(ohlc_index) and ohlc_index[end_loc_insert] == week_end_date: end_loc = end_loc_insert # Adjust if end is exact match
                        #             if start_loc >= len(ohlc_index) or end_loc < 0 or start_loc > end_loc: continue
                        #             
                        #             # Plot Mon High and Low lines for this week span
                        #             line_width = 1.5
                        #             line_style = '-'
                        #             line_color = '#00BCD4' # Cyan color
                        #             if not pd.isna(mon_high): 
                        #                 ax.plot(range(start_loc, end_loc + 1), [mon_high]*(end_loc - start_loc + 1), 
                        #                         color=line_color, linestyle=line_style, linewidth=line_width, label='MonHigh (Rot Wk)' if week_str==rotation_status.index[0] else "") # Label once
                        #             if not pd.isna(mon_low):  
                        #                 ax.plot(range(start_loc, end_loc + 1), [mon_low]*(end_loc - start_loc + 1), 
                        #                         color=line_color, linestyle=line_style, linewidth=line_width, label='MonLow (Rot Wk)' if week_str==rotation_status.index[0] else "") # Label once
                        # 
                        #         except Exception as e_loc:
                        #             print(f"Warning: Could not plot Mon H/L lines for week {week_str}: {e_loc}")
                        # --------------------------------------

                        # --- Plot session lines using integer indices (Remains the same) --- 
                        if not (selected_tf_freq.endswith('D') or selected_tf_freq.startswith('W')):
                            st.info(f"Overlaying structure for {len(sessions_in_range)} sessions...")
                            line_colors = {'Asia': 'blue', 'London': 'purple', 'NewYork': 'grey'}
                            poc_style = '--'
                            va_style = ':'
                            ohlc_index = ohlc_data.index
                            for idx, session_row in sessions_in_range.iterrows():
                                s_start = session_row['SessionStart']
                                s_end = session_row['SessionEnd']
                                s_poc = session_row['TPO_POC']
                                s_vah = session_row['VAH']
                                s_val = session_row['VAL']
                                s_name = session_row['Sessions']
                                s_color = line_colors.get(s_name, 'black')
                                try:
                                    start_loc = ohlc_index.searchsorted(s_start)
                                    end_loc_insert = ohlc_index.searchsorted(s_end)
                                    end_loc = end_loc_insert - 1 
                                    if end_loc_insert < len(ohlc_index) and ohlc_index[end_loc_insert] == s_end:
                                        end_loc = end_loc_insert
                                    if start_loc >= len(ohlc_index) or end_loc < 0 or start_loc > end_loc: continue 
                                except Exception: continue 
                                if not pd.isna(s_poc): ax.plot(range(start_loc, end_loc + 1), [s_poc]*(end_loc - start_loc + 1), color=s_color, linestyle=poc_style, linewidth=1.2)
                                if not pd.isna(s_vah): ax.plot(range(start_loc, end_loc + 1), [s_vah]*(end_loc - start_loc + 1), color=s_color, linestyle=va_style, linewidth=1.0)
                                if not pd.isna(s_val): ax.plot(range(start_loc, end_loc + 1), [s_val]*(end_loc - start_loc + 1), color=s_color, linestyle=va_style, linewidth=1.0)
                        else:
                            st.info("Session structure lines hidden for Daily or longer timeframes.")

                        st.pyplot(fig)
                        plt.close(fig)

                    except Exception as e:
                        st.error(f"Error generating mplfinance plot: {e}")
                else:
                    st.warning("No OHLC data generated for the selected range/timeframe.")
            else:
                 st.warning(f"Could not load tick data for the selected range.")
else:
    st.error("Failed to load session summary data. Cannot display application.")

# --- Optional: Display Column Explanations (as before) ---
st.markdown("--- ")
st.subheader("Column Explanations")
st.markdown("""
*   **Date**: Calendar date of the session.
*   **Sessions**: Name of the trading session (Asia, London, NewYork).
*   **SessionStart / SessionEnd**: Start and End Timestamps (UTC) of the session based on data.
*   **SessionOpen / SessionHigh / SessionLow / SessionClose**: OHLC prices for the session.
*   **SessionVolume**: Total volume traded during the session.
*   **SessionDelta**: Total delta (Ask Volume - Bid Volume) during the session.
*   **SessionTicks**: Number of price ticks recorded during the session.
*   **SessionVPOC**: Volume Point of Control (Price level with highest volume).
*   **TPO_POC**: Time Price Opportunity Point of Control (Price level visited most often in TPO periods).
*   **VAH / VAL**: Value Area High/Low (Range containing ~68% of TPOs around TPO_POC).
*   **IB_High / IB_Low**: Initial Balance High/Low (Range of first N TPO periods, typically 1 hour).
*   **PoorHigh / PoorLow**: Boolean indicating if the session extreme is potentially "poor" (unfinished auction).
*   **PoorHighPrice / PoorLowPrice**: Price of the poor extreme, if applicable.
*   **SinglePrints**: Boolean indicating if significant single prints exist in the TPO profile.
*   **SessionASR**: Average Session Range (SessionHigh - SessionLow).
""") 