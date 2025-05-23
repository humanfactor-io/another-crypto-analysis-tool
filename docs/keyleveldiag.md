# keyleveldiag.py – Quick Diagnostic for Key‑Level Touches

> Tracks how often recent BTC ticks come within a user‑defined tolerance
> of the latest **Weekly / Monthly / Quarterly / Yearly opens** stored in
> `btc_key_levels`.
>
> Version documented: commit as of May 2025

---

## Purpose
`keyleveldiag.py` is a throw‑away analysis helper – it does **not** write
back to the database.  It pulls:  
* the most recent row from **`btc_key_levels`** (generated by
  `derive_key_levels.py`) and extracts open prices for the four higher
  time‑frames, then  
* counts how many raw **ticks** came within a 15‑tick window of any of
  those prices.

This is useful for sanity‑checking key‑level accuracy or gauging how
"magnetic" a level has been intraday.

---

## Processing Steps

```text
┌───────────────────┐   ┌────────────────────────────┐   ┌─────────────────┐
│ Connect to SQLite │→ │ Read ticks.parquet (Last)  │→ │ Validate numeric │
└───────────────────┘   └────────────────────────────┘   └─────────────────┘
           │                                                  │
           ▼                                                  ▼
┌──────────────────────────┐   ┌───────────────────────────┐   ┌────────────────────┐
│ Query btc_key_levels for │→ │ Extract    lvl_vals array │→ │ np.abs price diff   │
│ latest SessionStartUTC   │   └───────────────────────────┘   └────────────────────┘
           │                                                           │
           ▼                                                           ▼
              ┌────────────────────────────┐   ┌──────────────────────┐
              │  any(|tick‑lvl| ≤ tol) per │→ │ Sum hits; print stats │
              │         tick (NumPy)       │   └──────────────────────┘
              └────────────────────────────┘
```

---

## Code Walk‑through

1. **Imports & DB connection**
   ```python
   conn = sqlite3.connect("crypto_data.db")
   ```

2. **Load ticks** (`ticks.parquet`)
   * Requires a `Last` column (numeric).
   * Rows with `NaN` in `Last` are dropped.

3. **Load key levels**
   ```sql
   SELECT WeeklyOpen, MonthlyOpen, QuarterlyOpen, YearlyOpen
   FROM btc_key_levels
   ORDER BY SessionStartUTC DESC
   LIMIT 1;
   ```
   Returns a single row; `NaN` columns are stripped before use.

4. **Vectorised hit detection** – tolerance hard‑coded to **15** price
   **ticks**:
   ```python
   diffs = np.abs(tick_prices[:, None] - lvl_vals_np)
   hits  = np.any(diffs <= tolerance, axis=1)
   ```

5. **Output**
   Prints the level values and the total number of tick rows that met the
   condition.

6. **Cleanup** – closes the SQLite connection.

---

## Usage
```bash
python keyleveldiag.py
```
Pre‑requisites:
* `crypto_data.db` must exist and contain a populated
  `btc_key_levels` table.
* `ticks.parquet` (raw tick data with `Last` price column) must be in
  the project root.

Optional adjustments:
* **Tolerance** – change the `tolerance = 15` line to widen/narrow the
  window.
* **Different levels** – edit the SQL to pull whatever columns you like
  (e.g., `WeeklyHigh`, `VAL`).

---

## Typical Output
```text
Level values checked: [ 67148.33  68724.1   42190.77  16819.77 ]
Number of ticks touching any key level (within 15): 148
Script finished.
```

---

## Limitations / TODO
* Assumes tick size is uniform; tolerance is applied as *absolute price
  difference*, not percentage.
* Works on **CPU memory**; extremely large `ticks.parquet` may exhaust
  RAM – consider chunked processing.
* Could be extended to output hit timestamps or visualise touches over
  time. 