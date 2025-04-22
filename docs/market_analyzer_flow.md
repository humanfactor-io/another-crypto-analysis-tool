# market_analyzer.py – Processing Flow

> Version documented: commit as of May 2025

This document explains **what happens, in what order, and why** when you
run

```bash
python market_analyzer.py [--file <NORMALISED_TICK_FILE>] [--rebuild]
```

The script ingests Binance-style normalised tick data (or reloads an
existing SQLite database), derives a rich set of session-level and daily
metrics, and persists the results in **`crypto_data.db`** for downstream
analytics.

---

## High-level pipeline

```text
┌────────────────┐        ┌───────────────┐      ┌─────────────────┐
│ CLI Arguments  │──────►│ Load from DB? │──Yes►│ Read SQLite DB  │
└────────────────┘        └───────────────┘      └─────────────────┘
          │ No                                          │
          ▼                                             ▼
┌────────────────────┐  ┌───────────────────┐   ┌───────────────────┐
│ load_and_preprocess│→│ calculate_delta   │→ │ get_active_sessions│
└────────────────────┘  └───────────────────┘   └───────────────────┘
          │                                   (adds `Sessions` list)
          │
          ▼
┌────────────────────┐   ┌────────────────────┐
│ calculate_daily_*  │   │ calculate_session_*│
│   (OHLC/Volume)    │   │   (OHLC/Delta)     │
└────────────────────┘   └────────────────────┘
          │                         │
          │                         ▼
          │                ┌────────────────────┐
          │                │  calculate_atr     │
          │                └────────────────────┘
          ▼                         │
┌────────────────────┐              ▼
│ calculate_session_ │   ┌──────────────────────────┐
│     vpoc           │   │ calculate_tpo_metrics    │
└────────────────────┘   └──────────────────────────┘
          │                         │
          └──────────────┬──────────┘
                         ▼
                ┌────────────────────┐
                │  save_to_database  │
                └────────────────────┘
```

---

## Detailed walk-through

### 1. CLI argument parsing
* `--file` : path to **normalised** tick file. Default
  `BTCUSDT_PERP_BINANCE_normalized.txt`.
* `--rebuild`: ignore any existing `crypto_data.db` and rebuild it from
  the provided file.

### 2. Decide data source
```
LOAD_FROM_DB = os.path.exists(DB_FILE) and (not args.rebuild)
```
* If the DB exists **and** `--rebuild` was *not* supplied → load three
  tables (`tick_data`, `daily_summary`, `session_summary`) straight from
  SQLite.
* Otherwise start a full file-based pipeline.

### 3. `load_and_preprocess_data()`
Reads the normalised CSV into a `DataFrame` and:
1. Converts `Timestamp` to `datetime64[ns]` (UTC).
2. Coerces OHLCV columns to numeric.
3. Adds a `Date` column (`Timestamp.dt.date`).

### 4. `calculate_delta()`
Adds `Delta = AskVolume − BidVolume` per tick.

### 5. `get_active_sessions()` → *Sessions column*
Vectorised application of the session calendar in `config.SESSIONS` to
label each tick with **one or more** session names.

### 6. Daily summary – `calculate_daily_summary()`
Produces per-day OHLC/Volume/Delta (first, max, min, last, sum).

### 7. Session summary – `calculate_session_summary()`
Explodes the multi-label `Sessions` column so overlapping sessions each
receive their own aggregated OHLCV/Delta rows keyed by
`(Date, SessionName)`.

Resulting columns include:
* `SessionStart`, `SessionEnd`
* `SessionOpen`, `SessionHigh`, `SessionLow`, `SessionClose`
* `SessionVolume`, `SessionDelta`, `SessionTicks`

### 8. ATR – `calculate_atr()`
Computes a *n*=14 (configurable) **Average True Range** on the daily
summary.

### 9. VPOC – `calculate_session_vpoc()`
For every `(date, session)`:
* Buckets prices to one-decimal bins.
* Sums volume per price.
* Adds `SessionVPOC` (Volume Point of Control).

### 10. Market Profile / TPO – `calculate_tpo_metrics()`
Derives:
* **TPO_POC, VAH, VAL** (70 % value area)
* **IB_High / IB_Low** (first *N* TPO periods)
* Boolean **PoorHigh / PoorLow** flags + their prices
* Boolean **SinglePrints** flag (configurable threshold or USD span)

Parameters pulled from `config`:
* `TPO_PERIOD_MINUTES`
* `PRICE_STEP`
* `VALUE_AREA_PERCENT`
* `INITIAL_BALANCE_PERIODS`
* Thresholds for single prints & poor extremes.

### 11. Session ASR (Average Session Range)
Adds `SessionASR = SessionHigh − SessionLow` (1-dp rounding).

### 12. `save_to_database()`
Writes the three DataFrames back to **`crypto_data.db`**:
* `tick_data` — full tick history (JSON-encoded `Sessions`)
* `daily_summary` — one row per calendar day
* `session_summary` — one row per `(date, session)` with all derived
  columns (ATR, VPOC, TPO, ASR…)

SQLite type considerations handled:
* `datetime` → string ISO format
* boolean flags → `INTEGER` 0/1
* lists → JSON strings

---

## Key functions reference
| Function | Purpose | Key Outputs |
| -------- | ------- | ----------- |
| `load_and_preprocess_data` | Read & clean tick CSV | DataFrame w/ `Date` |
| `calculate_delta` | Adds order-flow delta | `Delta` column |
| `calculate_daily_summary` | Daily OHLCV/Delta | `daily_summary` DF |
| `calculate_session_summary` | Session OHLCV/Delta | `session_summary` DF |
| `calculate_atr` | Average True Range | `ATR` column on daily |
| `calculate_session_vpoc` | Volume POC per session | `SessionVPOC` |
| `calculate_tpo_metrics` | Market-Profile stats | `TPO_POC`, `VAH`, `VAL`, `IB_*`, `Poor*`, `SinglePrints` |

---

## Config dependencies
`market_analyzer.py` uses parameters and structures defined in
`config.py`, notably:
* `SESSIONS` (dict of session names → `(start_time, end_time)`)
* `ATR_PERIOD`, `TPO_PERIOD_MINUTES`, `PRICE_STEP`, `VALUE_AREA_PERCENT`,
  `INITIAL_BALANCE_PERIODS`, `POOR_EXTREME_TPO_THRESHOLD`,
  `SINGLE_PRINT_THRESHOLD`, `SINGLE_PRINT_MIN_SPAN`

Modify `config.py` to tweak behaviour without touching the pipeline
code.

---

## Running examples
* **Initial build** – ingest full file and create DB:
  ```bash
  python market_analyzer.py --file BTCUSDT_PERP_BINANCE_normalized.txt --rebuild
  ```

* **Incremental run** – load existing DB, skip heavy calculations when
  possible:
  ```bash
  python market_analyzer.py
  ```

* **Debug TPO only for first 5 days:**
  Set `TPO_DATE_LIMIT = 5` near the top of the script or temporarily edit
  the constant before running.

---

## Output tables snapshot

```sql
.session_summary
─────────────────────────────────────────────────────────────────────────
Date        TEXT (YYYY-MM-DD)
Sessions    TEXT (e.g., 'London')
SessionStart TEXTISO
SessionEnd   TEXTISO
SessionOpen  REAL
SessionHigh  REAL
SessionLow   REAL
SessionClose REAL
SessionVolume REAL
SessionDelta REAL
SessionTicks INTEGER
SessionVPOC  REAL
TPO_POC      REAL
VAH          REAL
VAL          REAL
IB_High      REAL
IB_Low       REAL
PoorHigh     INTEGER (0|1)
PoorHighPrice REAL
PoorLow      INTEGER
PoorLowPrice REAL
SinglePrints INTEGER
SessionASR   REAL
```

Consult `database_schema.md` for the complete, up-to-date schema. 