## Session Summary Data Points

This table contains aggregated data and calculated metrics for each defined trading session (Asia, London, NewYork), typically stored in the `session_summary` table of `crypto_data.db`.

*   **Date**: The calendar date (YYYY-MM-DD) of the session.
    *   *Variable:* `Date`
*   **Sessions**: The name of the trading session ('Asia', 'London', 'NewYork').
    *   *Variable:* `Sessions`
*   **SessionStart**: Timestamp of the first tick recorded within this session on this date.
    *   *Variable:* `SessionStart`
*   **SessionEnd**: Timestamp of the last tick recorded within this session on this date.
    *   *Variable:* `SessionEnd`
*   **SessionOpen**: The 'Open' price of the first tick in the session.
    *   *Variable:* `SessionOpen`
*   **SessionHigh**: The highest 'High' price reached during the session.
    *   *Variable:* `SessionHigh`
*   **SessionLow**: The lowest 'Low' price reached during the session.
    *   *Variable:* `SessionLow`
*   **SessionClose**: The 'Close' price of the last tick in the session.
    *   *Variable:* `SessionClose`
*   **SessionVolume**: Total volume traded during the session.
    *   *Variable:* `SessionVolume`
*   **SessionDelta**: Total delta (AskVolume - BidVolume) accumulated during the session.
    *   *Variable:* `SessionDelta`
*   **SessionTicks**: The total number of ticks (price updates) recorded during the session.
    *   *Variable:* `SessionTicks`
*   **SessionVPOC**: Volume Point of Control for the session (the price level with the highest traded volume within the session).
    *   *Variable:* `SessionVPOC`
*   **TPO_POC**: Time Price Opportunity Point of Control for the session (the price level visited during the most TPO time periods within the session).
    *   *Variable:* `TPO_POC`
*   **VAH**: Value Area High for the session (the upper boundary of the TPO value area, typically containing `VALUE_AREA_PERCENT` of TPOs around the TPO POC).
    *   *Variable:* `VAH`
*   **VAL**: Value Area Low for the session (the lower boundary of the TPO value area).
    *   *Variable:* `VAL`
*   **IB_High**: Initial Balance High (the highest price reached during the first `INITIAL_BALANCE_PERIODS` TPO periods).
    *   *Variable:* `IB_High`
*   **IB_Low**: Initial Balance Low (the lowest price reached during the first `INITIAL_BALANCE_PERIODS` TPO periods).
    *   *Variable:* `IB_Low`
*   **PoorHigh**: Boolean (`True`/`False`) indicating if the session high is considered "poor" (an unfinished auction, touched by >= `POOR_EXTREME_TPO_THRESHOLD` TPO periods).
    *   *Variable:* `PoorHigh`
*   **PoorHighPrice**: The actual price level of the Poor High, if `PoorHigh` is `True` (otherwise NaN/None).
    *   *Variable:* `PoorHighPrice`
*   **PoorLow**: Boolean (`True`/`False`) indicating if the session low is considered "poor" (an unfinished auction, touched by >= `POOR_EXTREME_TPO_THRESHOLD` TPO periods).
    *   *Variable:* `PoorLow`
*   **PoorLowPrice**: The actual price level of the Poor Low, if `PoorLow` is `True` (otherwise NaN/None).
    *   *Variable:* `PoorLowPrice`
*   **SinglePrints**: Boolean (`True`/`False`) indicating if the session's TPO profile contains a sequence of consecutive single-print price levels meeting or exceeding the `SINGLE_PRINT_THRESHOLD`.
    *   *Variable:* `SinglePrints`
*   **SessionASR**: Average Session Range, calculated as `SessionHigh - SessionLow`.
    *   *Variable:* `SessionASR` 