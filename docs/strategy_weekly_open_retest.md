# Backtesting Strategy: Timing of Weekly Open Retest

## Strategy Overview

This strategy analyzes how often and when the Weekly Open price is revisited within the same calendar week. The goal is to determine the historical probability that the *first retest* occurs in a specific subsequent session of that week.

## Key Concepts

*   **Week Definition:** Starts Monday at 00:00 UTC.
*   **Weekly Open Price:** The `SessionOpen` price of the *first* session recorded on or after Monday 00:00 UTC for that week (typically Monday Asia).
*   **Retest:** A session "retests" the Weekly Open if the Weekly Open price falls within that session's high-low range (`SessionLow <= WeeklyOpen <= SessionHigh`).
*   **First Retest:** We are interested in the *first* session *after* the opening session (but within the same week) where the retest condition is met.
*   **Analysis Scope:** All sessions within the same calendar week (Monday to Sunday, relative to the opening session).

## Data Source

*   `session_summary` table from `crypto_data.db`.
*   Script used: `weekly_open_retest_analyzer.py`

## Results (Based on 16 Complete Weeks Analyzed)

The following table shows the probability of the *first* retest of the Weekly Open occurring in each subsequent session of the week.

| Session Number in Week | Approx. Session Name | Probability of First Retest |
| :--------------------- | :------------------- | :-------------------------- |
| Session 2              | Mon London           |                      43.75% |
| Session 3              | Mon NewYork          |                       6.25% |
| Session 4              | Tue Asia             |                      12.50% |
| Session 5              | Tue London           |                       6.25% |
| Session 6              | Tue NewYork          |                       6.25% |
| Session 7              | Wed Asia             |                       0.00% |
| Session 8              | Wed London           |                       0.00% |
| Session 9              | Wed NewYork          |                       6.25% |
| No Retest Within Week  |                      |                      18.75% |
| **Total**              |                      |                     100.00% |

## Interpretation

The Weekly Open price is most likely to be retested first during the second session of the week (Monday London), occurring ~44% of the time. Revisits become less frequent later in the week. There is a ~19% chance that the Weekly Open is not revisited at all within the same calendar week. 