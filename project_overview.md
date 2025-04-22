# Crypto Analysis – End‑to‑End Process Flow

> Quick read (≈2 min) for newcomers – shows **what happens, in which
> order, and which script/tool is responsible**.

---

## 1 Obtain raw data

| Action | Details |
| ------ | ------- |
| Export from Sierra Chart | **File → Export Bar/Trade Data** → choose *Tick* granularity → save as `.txt`. |
| Example output | `BTCUSDT_PERP_BINANCE.txt` |

---

## 2 Normalise timestamps

| Script | Purpose | Output |
| ------ | ------- | ------ |
| `normalize_timestamp.py` | • Splits the SC `Date` & `Time` columns,  <br>• converts to a single **UTC** `YYYY‑MM‑DD HH:MM:SS` field,  <br>• re‑orders OHLCV columns. | `BTCUSDT_PERP_BINANCE_normalized.txt` |

Optional: `filter_data.py` can slice the file to the last *N* lines ➜ `…_filtered.txt`. Useful for diagnostics.

---

## 3 Ingest, analyse & populate the database

| Script | Key tasks | Destination table(s) |
| ------ | --------- | -------------------- |
| `market_analyzer.py` | • Chunk‑reads the normalised file **or** reloads an existing DB. <br>• Adds `Sessions` (Asia/London/… + `LDN_NY_Overlap`).<br>• Builds **daily** & **session** summaries.<br>• Computes ATR, VPOC, Market‑Profile/TPO metrics, ASR.<br>• Saves everything to **`crypto_data.db`**. | `tick_data`, `daily_summary`, `session_summary` |
| `derive_key_levels.py` | Reads `session_summary`, derives **Weekly / Monthly / Monday / VWAP** key levels, saves to DB. | `btc_key_levels`, `session_vwap`, … |

---

## 4 Overlay additional key levels

Downstream scripts (e.g. `nvpoc_analyzer.py`, `weekly_open_retest_analyzer.py`) query `crypto_data.db` and overlay their derived lines on charts or export CSVs for further study.

---

## 5 Visual sanity check (Streamlit UI)

| File | What you get |
| ---- | ------------ |
| `data_viewer_app.py` | Streamlit dashboard with: <br>• Tabular views of all DB tables.<br>• Interactive price chart (Highcharts) where **key levels** can be toggled on/off.<br>Use it to verify that, e.g., Monday High matches TradingView. |
| `rotationviewerapp.py` | Lightweight variant focusing on weekly‑rotation stats. |

---

## 6 Run specialised back‑tests / analytics

| Script | Focus |
| ------ | ----- |
| `monday_stats_cli.py` | Monday range, Monday High/Low sweeps, session breaks. |
| `single_print_debug.py` | Integrity tests for Single‑Print detection. |
| `nvpoc_analyzer.py` | Naked vPOC statistics. |
| *…and many others in repo* | Each pulls from the DB, performs its own study, outputs CSV/plots. |

---

## 7 Global configuration

All tunable knobs live in **`config.py`** – session hours, ATR & TPO parameters, single‑print thresholds, exchange time‑zone offset, etc.

> Edit once – every script that `import config` will pick up the new
> settings.

---

## 8 Run everything in Docker (recommended)

Cursor integrates seamlessly with Docker, letting you spin up a fully‑isolated
Python environment (with all system libraries, Pandas, Streamlit, etc.) in **one
command**.  This avoids the "works on my machine" trap and keeps your local OS
clean.

| Step | Command | Notes |
| ---- | ------- | ----- |
| Build image | `docker build -t crypto-analysis .` | Only needed after cloning or when `requirements.txt` / code changes. |
| Launch interactive container | `docker run --rm -it -v $PWD:/app -p 8501:8501 crypto-analysis bash` | Mounts project dir read‑write and forwards the Streamlit port. |
| (Inside container) run pipeline | See cheat‑sheet below — commands are identical. |
| Stop container | `exit` | `--rm` flag auto‑removes the container. |

**Tip:**  Add a one‑liner in VS Code / Cursor *Run Task* panel:
```jsonc
{
  "label": "Docker Shell",
  "type": "shell",
  "command": "docker run --rm -it -v ${workspaceFolder}:/app -p 8501:8501 crypto-analysis bash"
}
```
So any new contributor can click and start hacking within seconds.

---

## Quick command cheat‑sheet

```bash
# ——— Local host or inside Docker shell ———
# (1) Normalise raw SC export
python normalize_timestamp.py BTCUSDT_PERP_BINANCE.txt

# (2) Ingest & build DB from scratch
python market_analyzer.py --file BTCUSDT_PERP_BINANCE_normalized.txt --rebuild

# (3) Compute key levels
python derive_key_levels.py

# (4) Launch Streamlit dashboard (port 8501 already forwarded by docker run)
streamlit run data_viewer_app.py --server.port 8501

# (5) Run Monday statistics back‑tester
python monday_stats_cli.py --weeks 26
```

Happy analysing 🚀 