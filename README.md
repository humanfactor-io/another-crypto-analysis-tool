# Crypto Analysis 🪙📈

End‑to‑end research environment for **Bitcoin / crypto tick data** – from
raw Sierra Chart exports to interactive dashboards and statistical
back‑tests, all reproducible in Docker.

---
## Disclaimers

- Don't download and run shit you don't understand. Perform your own due diligence.
- All analysis files in In_Development require varying levels of work to complete.

## Features

| Category | Highlights |
| -------- | ---------- |
| Data ingestion | • Chunked loader for multi‑GB Binance tick files<br>• Timestamp normaliser with millisecond precision |
| Database | • Single SQLite file (`crypto_data.db`) holding *tick*, *daily*, *session* tables<br>• Auto‑enriched with ATR, VPOC, TPO metrics, ASR |
| Key levels | • Weekly / Monthly / Quarterly / Yearly opens<br>• Monday range, rolling VWAP windows<br>• Naked vPOC detection |
| Visualization | • Streamlit app (`data_viewer_app.py`) with price chart & toggleable overlays |
| Back‑testing | CLI scripts for Monday stats, rotation trades, weekly‑open retest, etc. |
| Config‑first | All tunables in `config.py` – session hours, TPO params, single‑print thresholds |
| Docker | One‑command setup – *no local Python hassles* |

---

## Quick start (Docker)

```bash
# 1. Build the image (one‑time)
docker build -t crypto-analysis .

# 2. Drop into a container (mounts project & forwards Streamlit port)
docker run --rm -it -v $PWD:/app -p 8501:8501 crypto-analysis bash

# 3. Inside the container – run the pipeline
python normalize_timestamp.py BTCUSDT_PERP_BINANCE.txt
python market_analyzer.py --file BTCUSDT_PERP_BINANCE_normalized.txt --rebuild
python derive_key_levels.py
streamlit run data_viewer_app.py --server.port 8501
```
Open <http://localhost:8501> in your browser to explore the data.

---

## Local installation (via Docker)

Bare‑metal Python setup is **no longer supported** for this repository.
All scripts expect the libraries and system tooling baked into
`Dockerfile`.  Follow the *Quick start (Docker)* steps above:

1. `docker build -t crypto-analysis .`  – build the image once.
2. `docker run --rm -it -v $PWD:/app -p 8501:8501 crypto-analysis bash` –
   start an interactive shell with the project mounted.
3. Run the pipeline commands inside that container.

If you really must run natively, examine `Dockerfile` and replicate the
install commands in your own virtualenv – but issues opened for native
set‑ups will be closed as *out of scope.*

---

## Workflow in 7 steps

1. **Export tick file** from Sierra Chart → `BTCUSDT_PERP_BINANCE.txt`.
2. `normalize_timestamp.py` → `…_normalized.txt`.
3. `filter_data.py` *(optional)* slice for quick tests.
4. `market_analyzer.py` ingests file, builds `crypto_data.db`.
5. `derive_key_levels.py` adds weekly/monthly/Monday levels & VWAP.
6. `data_viewer_app.py` Streamlit dashboard → visual sanity check.
7. Run specialised scripts (`monday_stats_cli.py`, `nvpoc_analyzer.py`, …).

Full process flow is documented in `docs/project_overview.md`.

---

## Project structure

```
.
├── normalize_timestamp.py    # step‑1 cleaner
├── filter_data.py            # optional slice
├── market_analyzer.py        # heavy‑lift: sessions, TPO, DB
├── derive_key_levels.py      # weekly/monthly/Monday levels
├── data_viewer_app.py        # Streamlit UI
├── config.py                 # global parameters
├── docs/                     # extra documentation
└── requirements.txt
```

---

## Contributing

1. Fork → feature branch → PR.
2. Follow the existing code style (black + isort).
3. No large (>100 MB) artefacts in commits – use `.gitignore` or Git LFS.

---

## License

MIT – see `LICENSE` file. 
