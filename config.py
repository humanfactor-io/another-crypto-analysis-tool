# Configuration parameters for TPO analysis

# --- TPO Parameters ---
TPO_PERIOD_MINUTES = 30
PRICE_STEP = 1.0
VALUE_AREA_PERCENT = 0.68 # 68%
INITIAL_BALANCE_PERIODS = 2 # Corresponds to 1 hour with 30-min TPO periods
SINGLE_PRINT_THRESHOLD = 3 # Minimum number of consecutive single prints to flag (Updated as per spec)
SINGLE_PRINT_MIN_SPAN  = 20.0
POOR_EXTREME_TPO_THRESHOLD = 2 # Min TPO periods at extreme to be considered poor (Updated)

# --- Other Parameters (can be added later) ---
# Example: ATR_PERIOD = 14 

# ATR Calculation Parameter
ATR_PERIOD = 14 # Period for ATR calculation on daily data

# Session Definitions (UTC)
import datetime
SESSIONS = {
    # Standard Weekday Sessions (Mon-Fri)
    'Asia': (datetime.time(0, 0), datetime.time(9, 0)),
    'London': (datetime.time(7, 0), datetime.time(16, 0)),
    'NewYork': (datetime.time(13, 30), datetime.time(21, 0)),
    # Overlap window where both London and NewYork are active
    'LDN_NY_Overlap': (datetime.time(13, 30), datetime.time(16, 0)),

    # Overnight Gap Session (Represents Mon 21:00 -> Tue 00:00, etc. & Fri 21:00 -> Sat 00:00)
    'Overnight': (datetime.time(21, 0), datetime.time(0, 0)), 

    # Weekend Sessions (Full 24h Blocks)
    'Weekend-Sat': (datetime.time(0, 0), datetime.time(0, 0)), # Sat 00:00 to Sun 00:00
    'Weekend-Sun': (datetime.time(0, 0), datetime.time(0, 0))  # Sun 00:00 to Mon 00:00
} 

# Offset hours of exchange relative to UTC. Example: 0 for UTC‑quoted BTCUSDT, 8 for HK/SG exchanges
EXCHANGE_TZ = "America/New_York"      # handles DST, or None
EXCHANGE_UTC_OFFSET_HRS = 0           # ignored if EXCHANGE_TZ is set

# Single Print Definition Parameters 

