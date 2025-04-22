import pandas as pd
import sqlite3
import os
from datetime import datetime, timedelta

DB_FILE = "crypto_data.db"

def load_session_summary_data(db_path):
    """Loads the session_summary table from the SQLite database, sorted chronologically."""
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at: {db_path}")
        return None
        
    print(f"Loading session_summary from {db_path}")
    try:
        with sqlite3.connect(db_path) as conn:
            if pd.io.sql.has_table('session_summary', conn):
                # Load data, parsing dates
                df = pd.read_sql('SELECT * FROM session_summary', conn, 
                                 parse_dates=['Date', 'SessionStart', 'SessionEnd'])
                
                # Ensure correct Date type and sort
                df['Date'] = pd.to_datetime(df['Date']).dt.date
                df = df.sort_values(by=['Date', 'SessionStart']).reset_index(drop=True)
                
                # Ensure required columns exist
                required_cols = ['Date', 'Sessions', 'SessionStart', 'SessionEnd', 'SessionLow', 'SessionHigh', 'SessionVPOC']
                if not all(col in df.columns for col in required_cols):
                    missing = [col for col in required_cols if col not in df.columns]
                    print(f"Error: Missing required columns in session_summary: {missing}")
                    return None
                    
                print(f"Loaded and sorted {len(df)} rows from session_summary.")
                print(f"Columns found: {df.columns.tolist()}")
                return df
            else:
                print("Error: 'session_summary' table not found in the database.")
                return None
    except sqlite3.Error as e:
        print(f"Database error during load: {e}")
        return None
    except Exception as e:
         print(f"An error occurred during database load: {e}")
         return None

if __name__ == "__main__":
    print("Starting NVPOC Analysis...")
    session_df = load_session_summary_data(DB_FILE)

    if session_df is not None:
        print("Session summary data loaded successfully.")
        
        active_nvpocs = [] # Stores {'price': float, 'created_index': int, 'created_start': datetime}
        revisit_results = [] # Stores {'nvpoc_price': float, 'created_index': int, 'created_start': datetime, 
                             #          'revisit_index': int, 'revisit_start': datetime, 'sessions_elapsed': int}

        total_sessions = len(session_df)
        print(f"\nProcessing {total_sessions} sessions...")

        for current_index, current_session in session_df.iterrows():
            current_low = current_session['SessionLow']
            current_high = current_session['SessionHigh']
            current_start = current_session['SessionStart']
            current_vpoc = current_session['SessionVPOC']

            # Iterate through a copy for safe removal
            nvpocs_to_remove = []
            for i, nvpoc in enumerate(active_nvpocs):
                nvpoc_price = nvpoc['price']
                
                # Check for revisit
                if pd.notna(current_low) and pd.notna(current_high) and pd.notna(nvpoc_price):
                    if current_low <= nvpoc_price <= current_high:
                        # Revisit occurred
                        sessions_elapsed = current_index - nvpoc['created_index']
                        revisit_results.append({
                            'nvpoc_price': nvpoc_price,
                            'created_index': nvpoc['created_index'],
                            'created_start': nvpoc['created_start'],
                            'revisit_index': current_index,
                            'revisit_start': current_start,
                            'sessions_elapsed': sessions_elapsed
                        })
                        # Mark for removal
                        nvpocs_to_remove.append(i)
            
            # Remove revisited NVPOCs (iterate in reverse to handle index shifts)
            for index_to_remove in sorted(nvpocs_to_remove, reverse=True):
                del active_nvpocs[index_to_remove]

            # Add current session's VPOC as a potential NVPOC if it's valid
            if pd.notna(current_vpoc):
                active_nvpocs.append({
                    'price': current_vpoc,
                    'created_index': current_index,
                    'created_start': current_start
                })
                
            # Progress update (optional)
            if (current_index + 1) % 50 == 0 or (current_index + 1) == total_sessions:
                 print(f"  Processed session {current_index + 1}/{total_sessions}...")

        print("\nAnalysis Complete.")
        print(f"Total sessions processed: {total_sessions}")
        print(f"Total NVPOC revisits recorded: {len(revisit_results)}")
        print(f"Number of NVPOCs still active (not revisited): {len(active_nvpocs)}")
        
        # --- Calculate and display statistics ---
        if revisit_results:
            revisit_df = pd.DataFrame(revisit_results)
            
            # Calculate time elapsed in hours
            revisit_df['time_elapsed_hours'] = (revisit_df['revisit_start'] - revisit_df['created_start']) / timedelta(hours=1)
            
            # 24-hour filter
            revisited_within_24h = revisit_df[revisit_df['time_elapsed_hours'] <= 24]
            count_revisited_within_24h = len(revisited_within_24h)
            
            # Estimate total NVPOCs generated (assuming most sessions generate one)
            # A more precise count would track additions to active_nvpocs list
            # For now, use total revisits + remaining active as an estimate
            total_nvpocs_generated = len(revisit_results) + len(active_nvpocs)
            
            print("\n--- NVPOC Revisit Statistics ---")
            if total_nvpocs_generated > 0:
                percentage_revisited_within_24h = (count_revisited_within_24h / total_nvpocs_generated) * 100
                print(f"NVPOCs Revisited within 24 hours: {count_revisited_within_24h} / {total_nvpocs_generated} ({percentage_revisited_within_24h:.2f}%)")
            else:
                print("No NVPOCs were generated or revisited.")

            # Distribution by sessions elapsed
            print("\nDistribution of Revisits by Sessions Elapsed:")
            session_distribution = revisit_df['sessions_elapsed'].value_counts().sort_index()
            print(session_distribution)
            
            # Display first few rows of revisit data for context
            print("\nSample Revisit Data (First 5 Rows):")
            print(revisit_df.head())

        else:
            print("\nNo revisit data to analyze.")
        # -----------------------------------------------

    else:
        print("Failed to load session summary data. Exiting.") 