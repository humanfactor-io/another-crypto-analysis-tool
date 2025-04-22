# Backtesting Strategy: Timing of IB_Low Retest After NY Close Below IB

## Strategy Overview

This strategy analyzes the timing of price returning to the Initial Balance Low (`IB_Low`) after a New York trading session closes below that level. The goal is to determine the historical probability that the *first retest* of the specific `IB_Low` from that trigger New York session occurs in Session +1 (the subsequent session), Session +2, Session +3, etc., within a defined lookahead period.

## Key Concepts

*   **Initial Balance Low (IB_Low):** The lowest price level established during the first `INITIAL_BALANCE_PERIODS` (typically 1 hour) of a given trading session.
*   **Trigger Condition:** A New York session where the `SessionClose` price is strictly less than the `IB_Low` for that same session.
*   **Retest:** The specific `IB_Low` price level from the trigger (New York) session is considered "retested" if the price range (`[SessionLow, SessionHigh]`) of a subsequent session overlaps with or crosses this `IB_Low` level (`SessionLow <= trigger_IB_Low <= SessionHigh`).
*   **First Retest:** We are interested in the *first* subsequent session where the retest condition is met.
*   **Lookahead Period:** The number of subsequent sessions checked for the retest (analysis used N=5).

## Data Source

*   `session_summary` table from `crypto_data.db`.
*   Script used: `ib_low_retest_analyzer.py`

## Results (Based on 32 Trigger Events)

The following table shows the probability of the *first* retest occurring in each specific subsequent session following the trigger New York session.

| Subsequent Session | Session Name (Typical) | Probability of First Retest |
| :----------------- | :--------------------- | :-------------------------- |
| Session +1           | Asia                   |                      43.75% |
| Session +2           | London                 |                      15.62% |
| Session +3           | NewYork                |                       6.25% |
| Session +4           | Asia                   |                       6.25% |
| Session +5           | London                 |                       0.00% |
| **No Retest**      | (Within 5 Sessions)    |                      28.12% |
| **Total**          |                        |                     100.00% |

## Interpretation

When a New York session closes below its `IB_Low`, there's a ~44% chance that this level will be revisited during the following Asia session. The probability decreases in subsequent sessions, and there is a ~28% chance the level isn't revisited within the next 5 sessions. 