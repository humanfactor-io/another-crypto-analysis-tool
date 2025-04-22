# Backtesting Strategy: Monday Range Rotation (Session-Based)

## Objective

To test whether price is likely to rotate between the **Monday High**, **Monday Mid**, and **Monday Low** levels during the trading week. This strategy helps determine the probability of range-to-range movement and potential trap/reversal setups for scalping strategies.

---

## Strategy Structure

### Key Concepts:
- The **Monday Range** is established during Monday's full daily session (00:00–23:59 UTC or session-defined).
- Price is expected to interact with Monday's High, Low, and Mid throughout the rest of the week (Tuesday–Friday).
- We track whether the price rotates **from one extreme to the other**, which can be used for mean reversion or breakout-trap trades.

---

## Dataset Requirements

Your dataset should already include:
- `SessionStart`, `SessionHigh`, `SessionLow`, `SessionClose`
- `MondayHigh`, `MondayLow`, `MondayMid` (from your key level logic)
- `Week` column (using `SessionStart.dt.to_period('W')`)

---

##  Example Trade Logic 
If price breaks above Monday High on Tuesday,
and then returns to below Monday Mid on the same or a later session,
enter a short position with target = Monday Low.

---

## Metrics to track
rotation_stats.mean()	% of weeks where full Monday range rotation occurred
rotation_stats.sessionmean()    % probability of which session the rotation begins.

---

## Backtest Logic (EXAMPLE)

### Step 1: Define Rotational Flags

```python
df['TradedMondayHigh'] = df['SessionHigh'] >= df['MondayHigh']
df['TradedMondayLow'] = df['SessionLow'] <= df['MondayLow']
df['TradedMondayMid'] = (df['SessionHigh'] >= df['MondayMid']) & (df['SessionLow'] <= df['MondayMid'])

### Step 2: Group by Week and Calculate Rotation Events

```python
rotation_stats = df.groupby('Week')[['TradedMondayHigh', 'TradedMondayLow', 'TradedMondayMid']].any()
rotation_stats['FullRotation'] = rotation_stats['TradedMondayHigh'] & rotation_stats['TradedMondayLow']

### Step 3: Calculate Probabilities
```python
rotation_stats.mean()

---

## Defining a Failed Breakout

A breakout of Monday High (or Low) is considered **failed** if:

- Fewer than 4 consecutive 15-minute candles close above the level  
- OR price returns below the Monday Mid within the same session or next session  
- OR price crosses back under session VWAP within N candles after the breakout

This condition filters out false breakouts and improves signal quality for mean reversion trades.

You can experiment with different thresholds (e.g., 2 vs. 5 candles) in your backtest.