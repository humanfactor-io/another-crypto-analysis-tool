import sqlite3
import pandas as pd
import numpy as np
import textwrap
import datetime as dt

# Connect to the database
conn = sqlite3.connect("crypto_data.db")

# Load tick data
try:
    ticks = pd.read_parquet("ticks.parquet")
    # Ensure 'Last' column exists and is numeric
    if "Last" not in ticks.columns:
        raise ValueError("Missing 'Last' column in ticks.parquet")
    ticks["Last"] = pd.to_numeric(ticks["Last"], errors='coerce')
    ticks.dropna(subset=["Last"], inplace=True)
    if ticks.empty:
        raise ValueError("No valid tick data after loading and cleaning.")
except FileNotFoundError:
    print("Error: ticks.parquet not found.")
    conn.close()
    exit()
except Exception as e:
    print(f"Error loading or processing ticks.parquet: {e}")
    conn.close()
    exit()


# Load key levels
try:
    # Select relevant levels from the *most recent* entry in btc_key_levels
    # Ordering by SessionStartUTC descending and taking the first row
    key_query = """
        SELECT WeeklyOpen, MonthlyOpen, QuarterlyOpen, YearlyOpen
        FROM btc_key_levels
        ORDER BY SessionStartUTC DESC
        LIMIT 1;
    """
    key = pd.read_sql(key_query, conn)
    if key.empty:
        raise ValueError("No data found in btc_key_levels table.")
    # Get the values from the first (and only) row, drop NaNs
    lvl_vals = key.iloc[0].dropna().values
    if lvl_vals.size == 0:
         raise ValueError("No valid key level values found in the most recent btc_key_levels entry.")
except Exception as e:
    print(f"Error loading or processing key levels from database: {e}")
    conn.close()
    exit()

# --- Calculate hits using the corrected NumPy broadcasting approach ---

# Get tick prices as a NumPy array
tick_prices = ticks["Last"].to_numpy()

# Ensure lvl_vals is a NumPy array (already done by .values, but belt-and-suspenders)
lvl_vals_np = np.asarray(lvl_vals)

# Calculate absolute differences between each tick and all levels
# Resulting shape: (number_of_ticks, number_of_levels)
diffs = np.abs(tick_prices[:, None] - lvl_vals_np)

# Check if *any* level's difference is within the tolerance for each tick
# Tolerance set to 15 ticks as per the original code
tolerance = 15
hits_bool = np.any(diffs <= tolerance, axis=1)

# Convert boolean array back to a Pandas Series aligned with the original ticks index
hits = pd.Series(hits_bool, index=ticks.index)

# --- End of corrected calculation ---

# Print the total number of ticks that touched *any* of the specified levels
# Since 'hits' is now a 1D boolean Series, we just sum the True values
print(f"Level values checked: {lvl_vals_np}")
print(f"Number of ticks touching any key level (within {tolerance}): {hits.sum()}")

# Close the database connection
conn.close()

print("Script finished.")