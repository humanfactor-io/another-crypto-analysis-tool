## 1. Purpose and Objective

Validate the accuracy of our Python back‑testing application by measuring how often the Volume POC (nPoC) and TPO POC (tPoC) levels from each live trading session are revisited:

- **nPoC:** Price level with the highest traded volume in a session (`SessionVPOC` in `session_summary` table).  
- **tPoC:** Price level with the most TPO periods in a session (`TPO_POC` in `session_summary` table).  

We’ll track:
1. **Within‑session revisits** (does price revisit that session’s POC before it ends?)  
2. **Cross‑session revisits** (how many sessions later does price return to the POC?)

---

## 2. Data Sources & Prerequisites

1. **Python Environment**  
   - Python 3.8+  
   - `pandas`, `numpy`, `sqlite3` (or `SQLAlchemy`)  

2. **Database: `crypto_data.db`**  
   - **Table `session_summary`** (per‐session aggregates & POCs):  
     - `Date`, `Sessions`, `SessionStart` (UTC), `SessionEnd` (UTC),  
       `SessionVPOC`, `TPO_POC`, plus high/low/open/close and other profile fields.  
   - **Table `btc_key_levels`** (for reference only): previous‐session and period levels.  
   - **Table `session_vwap`** (rolling VWAPs—not directly used here).

3. **Tick Data File**  
   - **`BTCUSDT_PERP_BINANCE_normalized.txt`**:  
     - Contains timestamped trades or bars covering all ticks.  
     - At minimum: `timestamp` (UTC), `price`, `volume`.

4. **Tolerance Parameter**  
   - Price tolerance δ (e.g. half‐tick) for defining a “revisit.”

---

## 3. Calculation Method & Methodology

1. **Load POC Levels**  
   ```python
   import sqlite3
   import pandas as pd

   conn = sqlite3.connect('crypto_data.db')
   sessions = pd.read_sql('SELECT Date, Sessions, SessionStart, SessionEnd, SessionVPOC, TPO_POC FROM session_summary', conn)
2. **Stream or Chunk Tick Data**
   ```python
   ticks = pd.read_csv('BTCUSDT_PERP_BINANCE_normalized.txt', parse_dates=['timestamp'])

3. ***Define a Revisit Function***
    - Accepts one POC price, session time window, and tolerance δ.
    - Returns first revisit timestamp if any.
    ```python
    def find_revisit(df_ticks, poc_price, start, end, δ):
    mask = (df_ticks.timestamp >= start) & (df_ticks.timestamp <= end)
    hits = df_ticks[mask].loc[lambda d: (d.price - poc_price).abs() <= δ]
    return hits.timestamp.min() if not hits.empty else None

4.  ***Within‑Session Revisit Loop***
```python
δ = 0.5  # half‐tick tolerance
results = []
for _, row in sessions.iterrows():
    for poc_type in ['SessionVPOC', 'TPO_POC']:
        poc_price = row[poc_type]
        revisit = find_revisit(ticks, poc_price, row.SessionStart, row.SessionEnd, δ)
        Δt_within = (revisit - row.SessionStart).total_seconds()/60 if revisit else None
        results.append({
            'Date': row.Date,
            'Session': row.Sessions,
            'POC_Type': poc_type,
            'POC_Price': poc_price,
            'Revisited_Within': bool(revisit),
            'Δt_within_mins': Δt_within
        })

5. ***Cross-Session Revisit***
- For each session i and POC, scan the tick stream from SessionEnd[i] forward until you hit the level.
- Record session gap (count of sessions crossed) and timestamp difference.

6. ***Aggregate Metrics***
- Within‑Session Rate:
- % of POCs revisited before session close.
- Cross‑Session Rate:
- % revisited within N sessions and average session gap.
- Latency:
- Mean Δt_within and mean time to cross‑session hit.

7. ***Expected Behaviour*** 
- High Within‑Session Revisit Rate (range‐bound days): 60–80%.
- Cross‑Session Clustering:
    - POCs often see follow‑through in 1–3 sessions.
- Latency Profiles:
    - Fast sessions: Δt_within ≈ 5–15 mins.
    - Slow sessions: may show zero revisits.
- Data Integrity Checks:
    - Missing revisits → check tick ingestion/time alignment. 
    - Extra hits outside tolerance → verify δ.

7. ***Example Output***
| Date       | Session   | POC Type | POC Price | Revisited Within? | Δt_within (mins) | Cross‑Session Revisited? | Session Gap | Δt_cross (hh:mm) |
|------------|-----------|----------|-----------|-------------------|------------------|--------------------------|-------------|------------------|
| 2025‑04‑01 | London    | nPoC     | 28,450.0  | Yes               | 12.3             | Yes                      | 1           | 05:42            |
| 2025‑04‑01 | London    | tPoC     | 28,460.5  | No                | —                | Yes                      | 2           | 02:15            |
| 2025‑04‑02 | NewYork   | nPoC     | 28,500.0  | Yes               | 08.7             | No                       | —           | —                |
| 2025‑04‑02 | NewYork   | tPoC     | 28,495.0  | Yes               | 03.5             | Yes                      | 1           | 10:21            |

