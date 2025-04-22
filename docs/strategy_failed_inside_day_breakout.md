# Backtesting Strategy: Decisive Failed Inside Day Breakout (VAH -> VAL within D+1/D+2)

## Strategy Overview

This strategy aims to identify instances where the market forms an Inside Day, attempts to break out above the Value Area High (VAH) on the following day but fails to sustain the move (confirmed by hourly closes), and subsequently reverses decisively to test the Value Area Low (VAL) within the same day or the next day.

## Key Concepts

*   **Inside Day (Day D):** A trading day where the `DailyHigh < PreviousDayHigh` AND `DailyLow > PreviousDayLow`. This signifies consolidation.
*   **Dynamic Overlap Lookback Period:** Starting from the Inside Day (Day D), we look back day by day (`D` vs `D-1`, `D-1` vs `D-2`, etc.). We continue including prior days as long as the Value Area (using the reference session, e.g., New York) of consecutive days overlaps by 50% or more (`calculate_va_overlap_percentage >= 0.50`). The lookback stops when the overlap drops below 50%.
*   **Reference Value Area (RefVAH / RefVAL - Proxy):** Calculated by averaging the `VAH` and `VAL` values (from the reference session) of *all* the days included in the dynamic overlap lookback period ending on Day D. This serves as a proxy for the true composite value area of that period.
*   **Breakout Attempt (Day D+1):** The day immediately following the Inside Day. We check if `Day D+1 DailyHigh >= RefVAH` (the calculated average VAH).
*   **Failed Breakout Confirmation (Hourly Close Check):** This confirms the failure to hold above VAH on the breakout attempt day (`Day D+1`). It requires two conditions based on 1-hour OHLC candles derived from tick data for `Day D+1`:
    1.  At least one hourly candle must have its `High >= RefVAH` (confirming the level was touched).
    2.  **No** hourly candle during the entire day (`Day D+1`) can have its `Close > RefVAH`.
*   **Decisive Reversal Target (Day D+1 or D+2):** The target is for the price to touch or break below the `RefVAL` (the calculated average VAL). This must occur quickly:
    *   Either `Day D+1 DailyLow <= RefVAL`
    *   OR `Day D+2 DailyLow <= RefVAL`

## Data Requirements

*   **`daily_summary` Table:** Required for identifying Inside Days (`Date`, `DailyHigh`, `DailyLow`) and checking the reversal target (`DailyLow`).
*   **`session_summary` Table:** Required to get the `VAH` and `VAL` for the identified Inside Day (`Day D`) to use as `RefVAH` and `RefVAL`. Assumes VAH/VAL are calculated for the session corresponding to the Inside Day (e.g., if using daily VAH/VAL, link that to the daily_summary table).
*   **Tick Data (`BTCUSDT_PERP_BINANCE_normalized.txt`):** Required for resampling into 1-hour candles on `Day D+1` to perform the Hourly Close Confirmation check. Needed columns: `Timestamp`, `High`, `Low`, `Close`.

## Strategy Logic Steps

1.  **Identify Inside Days (Day D):** Scan `daily_summary` data to find days meeting the Inside Day criteria.
2.  **Determine Dynamic Lookback & Reference VAH/VAL:** For each Inside Day (`Day D`):
    *   Calculate the lookback period by checking >= 50% VA overlap between consecutive days, starting from Day D and going backwards.
    *   Retrieve the `VAH` and `VAL` for the reference session (e.g., New York) for all days in the identified lookback period.
    *   Calculate the average of these VAHs (`RefVAH`) and VALs (`RefVAL`).
3.  **Check Initial Breakout & VAH Touch (Day D+1):** Check if `Day D+1 DailyHigh >= RefVAH` (using the calculated average `RefVAH`). If not, this sequence does not trigger.
4.  **Confirm Failed Breakout with Hourly Closes (Day D+1):**
    *   If Step 3 is true, load tick data for `Day D+1`.
    *   Resample ticks into 1-hour OHLC candles.
    *   Verify that at least one hourly `High >= RefVAH`.
    *   Verify that **NO** hourly `Close > RefVAH`.
    *   If both hourly conditions are met, `Day D+1` is a **Confirmed Trigger Day**.
5.  **Check for Decisive Reversal to VAL (Day D+1 / D+2):**
    *   If `Day D+1` is a Confirmed Trigger Day:
        *   Check if `Day D+1 DailyLow <= RefVAL` (using the calculated average `RefVAL`). If YES, record **Success (D+1)**.
        *   If NO, then check if `Day D+2 DailyLow <= RefVAL`. If YES, record **Success (D+2)**.
        *   If NO on both days, record **Failure**.

## Expected Backtesting Output / Metrics

*   Total number of Inside Days identified.
*   Number of potential triggers (`Day D+1 High >= RefVAH`).
*   Number of Confirmed Triggers (met potential trigger + hourly close conditions).
*   Number of successful reversals reaching `RefVAL` on Day D+1.
*   Number of successful reversals reaching `RefVAL` on Day D+2.
*   Total number of successful reversals.
*   Total number of failures (confirmed trigger but target not met by end of D+2).
*   Overall Success Rate (Total Successes / Confirmed Triggers).
*   Failure Rate (Total Failures / Confirmed Triggers).
*   Timing Breakdown: Probability of success occurring on D+1 vs D+2 (given a success occurred). 