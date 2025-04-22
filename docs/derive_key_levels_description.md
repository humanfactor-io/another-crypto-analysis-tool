# Rolling Key Level Extraction and SQLite Storage

## Purpose

This guide explains how to compute **rolling key levels** from session-based BTC data and store them in a **local SQLite database**. These levels can later be used to backtest reactions (touches, sweeps, rejections) for scalping strategies.

The logic now lives in `derive_key_levels.py` and operates **per trading session** that is kept in the `session_summary` table.

Key points of the 2025-05 update:

* Uses `SessionStartUTC` as the immutable foreign-key so downstream tables never lose the original timestamp.
* Applies `config.EXCHANGE_UTC_OFFSET_HRS` (or `EXCHANGE_TZ`) internally → creates `AdjSessionStart` just for resampling.  This guarantees Monday/weekly alignment with TradingView while preserving the raw key.
* New `LDN_NY_Overlap` session is kept; only `Overnight`, `Weekend-Sat`, `Weekend-Sun` are excluded by default (`EXCLUDE_SESSIONS`).
* Rolling VWAP windows are driven by the `VWAP_WINDOWS` list (30 & 365 by default).

---

## Prerequisites

You have a normalized session-level DataFrame called `df_sessions` with columns like: Date, SessionStart, SessionEnd, SessionOpen, SessionHigh, SessionLow, SessionClose, SessionVolume, etc. 
- Sessions are aligned by your `config.py` (e.g. defining Tokyo, London, New York sessions)
- Timestamps are normalised and consistent 
- You'll be using `pandas` and `sqlite3` (or `sqlalchemy` for optional ORM)

---

## Key Levels to Calculate (Per Session)

| Level Type  | Level Components                                      |
|-------------|-------------------------------------------------------|
| Daily       | Daily Open                                            |
| Monday      | Monday High/Low, Monday Range, Monday Mid             |
| Weekly      | Weekly Open, Previous Week High/Low, Previous Week Mid|
| Monthly     | Monthly Open, Previous Month High/Low, Mid            |
| Quarterly   | Quarterly Open, Previous Quarter Mid                  |
| Yearly      | Yearly Open, Previous Year Mid                        |

---

## Sample Output Table: `btc_key_levels`

| SessionDate | SessionOpen | DailyOpen | WeeklyOpen | WeeklyHigh | WeeklyMid | MondayMid | MondayRange | MonthlyOpen | MonthlyHigh | MonthlyLow | MonthlyMid | QuarterlyOpen | QuarterlyMid | YearlyOpen | YearlyMid |
|-------------|-------------|-----------|------------|-------------|------------|------------|--------------|--------------|--------------|-------------|-------------|----------------|---------------|-------------|------------|
| 2024-03-01  | 62000.0     | 62000.0   | 61800.0    | 63000.0     | 62400.0    | 62250.0    | 1000.0       | 60000.0      | 63500.0      | 58000.0     | 60750.0     | 58000.0        | 61000.0       | 50000.0     | 59000.0    |
| 2024-03-02  | 62500.0     | 62500.0   | 61800.0    | 63000.0     | 62400.0    | 62250.0    | 1000.0       | 60000.0      | 63500.0      | 58000.0     | 60750.0     | 58000.0        | 61000.0       | 50000.0     | 59000.0    |
| 2024-03-03  | 61500.0     | 61500.0   | 61800.0    | 63000.0     | 62400.0    | 62250.0    | 1000.0       | 60000.0      | 63500.0      | 58000.0     | 60750.0     | 58000.0        | 61000.0       | 50000.0     | 59000.0    |

---

## Output Table Formatting on the Web Front-End 
- this can be presented in a different table on the web-front end as the other summary data table is already large. 

