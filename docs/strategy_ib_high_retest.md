# Backtesting Strategy: Timing of IB_High Retest After NY Close Above IB

## Strategy Overview

This strategy analyzes the timing of price returning to the Initial Balance High (`IB_High`) after a New York trading session closes above that level. The goal is to determine the historical probability that the *first retest* of the specific `IB_High` from that trigger New York session occurs in Session +1 (the subsequent session), Session +2, Session +3, etc., within a defined lookahead period.

## Key Concepts

*   **Initial Balance High (IB_High):** The highest price level established during the first `INITIAL_BALANCE_PERIODS` (typically 1 hour) of a given trading session.
*   **Trigger Condition:** A New York session where the `SessionClose` price is strictly greater than the `IB_High` for that same session.
*   **Retest:** The specific `IB_High` price level from the trigger (New York) session is considered "retested" if the `SessionLow` of a subsequent session touches or breaks below this `IB_High` level (`SessionLow <= trigger_IB_High`).
*   **First Retest:** We are interested in the *first* subsequent session where the retest condition is met.
*   **Lookahead Period:** The number of subsequent sessions checked for the retest (analysis used N=5).

## Data Source

*   `session_summary` table from `crypto_data.db`.
*   Script used: `ib_high_retest_analyzer.py`

## Results (Based on 38 Trigger Events)

The following table shows the probability of the *first* retest occurring in each specific subsequent session following the trigger New York session.

| Subsequent Session | Session Name (Typical) | Probability of First Retest |
| :----------------- | :--------------------- | :-------------------------- |
| Session +1           | Asia                   |                      60.53% |
| Session +2           | London                 |                       5.26% |
| Session +3           | NewYork                |                       5.26% |
| Session +4           | Asia                   |                       0.00% |
| Session +5           | London                 |                       2.63% |
| **No Retest**      | (Within 5 Sessions)    |                      26.32% |
| **Total**          |                        |                     100.00% |

## Interpretation

When a New York session closes above its `IB_High`, there's a high probability (~61%) that this level will be revisited (touched or broken below by the session low) during the following Asia session. The probability drops significantly for subsequent sessions, and there is a ~26% chance the level isn't revisited within the next 5 sessions. 