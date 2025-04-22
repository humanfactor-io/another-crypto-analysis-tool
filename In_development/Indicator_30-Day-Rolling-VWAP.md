# 30-Day Rolling VWAP Strategy (Session-Based)

## Purpose

This document outlines a simple strategy using a 30-day rolling Volume Weighted Average Price (VWAP) based on daily (session-level) data. VWAP serves as a dynamic benchmark that reflects the average traded price, weighted by volume — useful for trend identification, mean reversion signals, and entry filtering.

---

## What is VWAP?

**VWAP** = (∑ Typical Price × Volume) / ∑ Volume  
Where:
- **Typical Price** = (High + Low + Close) / 3
- Volume = Total traded volume for the session

---

## Data Requirements

To compute VWAP at the **session level**, you'll need the following columns:

- `SessionHigh`
- `SessionLow`
- `SessionClose`
- `SessionVolume`

From this, we derive a session-level VWAP and apply a 30-session rolling average.

---

## Why Use Rolling VWAP?

The 30-session rolling VWAP acts as a **dynamic support/resistance** level or **fair value anchor**. Price action above the VWAP can signal a bullish environment; below it can indicate bearish bias. This is particularly helpful for:

- Trend-following breakout strategies
- Mean-reversion setups (e.g., fading overextensions from VWAP)
- Contextual filters for other signals (e.g., Initial Balance breakouts)

---

## Example: Calculating Rolling VWAP in Pandas

```python
import pandas as pd

# Assume df contains session-level data
df['SessionVWAP'] = (df['SessionHigh'] + df['SessionLow'] + df['SessionClose']) / 3

# 30-session rolling VWAP
df['VWAP_30'] = (
    (df['SessionVWAP'] * df['SessionVolume']).rolling(window=30).sum()
    / df['SessionVolume'].rolling(window=30).sum()
)
