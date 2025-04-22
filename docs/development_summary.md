# Development Summary

This document summarizes the development activities performed during our session.

## 1. Initial Setup & Review

*   Confirmed initial configuration parameters in `config.py`.
*   Reviewed project objectives and methodology from `Crypto Analysis Methodology.txt` and `Crypto Analysis Objectives.txt`.
*   Analyzed the existing Python scripts (`config.py`, `market_analyzer.py`, `filter_data.py`, `normalize_timestamp.py`, `data_viewer_app.py`) to understand the data processing workflow.
*   Clarified that `BTCUSDT_PERP_BINANCE_normalized.txt` serves as the preprocessed input for `market_analyzer.py`.
*   Identified that script execution and app deployment occur within a Docker container (`crypto-filter`).

## 2. TPO Calculation Testing & Threshold Calibration

*   **Initial Test:** Attempted to run `market_analyzer.py` within Docker, limiting TPO calculation to the first 10 days (`TPO_DATE_LIMIT = 10`) for testing purposes.
*   **Threshold Adjustments (Iterative Process):** We iteratively adjusted and tested the thresholds for `SINGLE_PRINT_THRESHOLD` and `POOR_EXTREME_TPO_THRESHOLD` in `config.py` based on analysis requirements and observations:
    *   Reviewed `advanced_feature_spec.txt` for initial guidance.
    *   Confirmed Poor High/Low logic in `market_analyzer.py` matched the spec (`>= 2` TPOs initially).
    *   Modified `config.py` and `market_analyzer.py` to make the Poor High/Low threshold configurable (`POOR_EXTREME_TPO_THRESHOLD`).
    *   Iteratively updated `config.py` with various threshold values:
        *   `SINGLE_PRINT_THRESHOLD`: 3 -> 5 -> 20 -> 50 -> 150
        *   `POOR_EXTREME_TPO_THRESHOLD`: 3 -> 4 -> 2
    *   For each threshold update, temporarily modified `market_analyzer.py` to force a full recalculation of TPO metrics across all sessions and executed the script within Docker.
    *   After each recalculation run, reverted the forced calculation logic in `market_analyzer.py` to its standard behavior.
*   **Final Thresholds Used for Calculation:** The last full recalculation saved to the database used `SINGLE_PRINT_THRESHOLD = 150` and `POOR_EXTREME_TPO_THRESHOLD = 2`.

## 3. Streamlit Frontend (`data_viewer_app.py`)

*   **Updates:**
    *   Updated the column descriptions in the markdown section to include TPO metrics.
    *   Changed the application title to "BTCUSDT.P Trading Session Summary Data".
*   **Execution Issues:** Encountered persistent issues when attempting to run the Streamlit app via Docker:
    *   Repeated "port is already allocated" errors for port 8501.
    *   Attempts to use port 8502 resulted in the container starting, the app loading data, but then immediately stopping, based on user-provided logs.
    *   This issue occurred even when the analysis script (`market_analyzer.py`) was run separately or in sequence before launching Streamlit.
    *   The root cause seems related to the Docker configuration or the Streamlit app's behavior within the container, rather than simple port conflicts or issues with the analysis script itself.

## 4. Naked Volume POC (NVPOC) Strategy Analysis

*   **Strategy Definition:** Read and parsed the requirements from `Strategy_Naked_vPOC.txt`.
*   **Clarification:** Confirmed that the NVPOC analysis would use the pre-calculated `session_summary` data, while the underlying TPO metrics (used for Poor High/Low, Single Prints) were derived from the tick data.
*   **Implementation (`nvpoc_analyzer.py`):**
    *   Created a new script `nvpoc_analyzer.py`.
    *   Implemented logic to load and sort session data from `crypto_data.db`.
    *   Implemented the core NVPOC tracking algorithm: iterating through sessions, maintaining a list of active NVPOCs, checking for revisits based on session high/low, and recording revisit details (including sessions elapsed).
    *   Added statistical calculations: calculating time elapsed (hours), identifying revisits within 24 hours, calculating the percentage revisited within 24h, and determining the distribution of revisits by sessions elapsed.
*   **Execution:** Ran the `nvpoc_analyzer.py` script in Docker, which successfully processed the data and produced the following key statistics:
    *   Total NVPOCs (estimated): 312
    *   Revisited within 24 hours: 262 / 312 (83.97%)
    *   Revisit Distribution: Showed a strong tendency for revisits within 1-2 sessions.

## 5. Current Status

*   `config.py` contains the latest threshold values (`SINGLE_PRINT_THRESHOLD = 150`, `POOR_EXTREME_TPO_THRESHOLD = 2`).
*   `crypto_data.db` contains `session_summary` data with TPO metrics calculated using these latest thresholds.
*   `nvpoc_analyzer.py` contains the completed session-level NVPOC revisit analysis and statistics calculation.
*   `data_viewer_app.py` has updated titles/descriptions but has unresolved issues running persistently within the Docker environment.

## 6. Additional Enhancements (May 2025)

* **Overlap Session Added** – Introduced a dedicated `LDN_NY_Overlap` session (13:30‑16:00 UTC) by adding it to `config.SESSIONS` and refactoring `get_active_sessions()` in `market_analyzer.py` to iterate over the dictionary dynamically.  Any tick in that 2½‑hour window is now tagged with `['London','NewYork','LDN_NY_Overlap']`.
* **Single‑Print Logic v2** – Replaced the original "≥ threshold consecutive" rule with a dual criterion:
  * flag if **≥ THRESH** almost‑consecutive (≤1 gap) single‑TPO levels **or**
  * the total single‑print span ≥ `SINGLE_PRINT_MIN_SPAN` USD.
  Defaults (`THRESH = 3`, `MIN_SPAN = 20.0`) live in `config.py`.
* **Monday‑stats CLI v2** – Re‑engineered `monday_stats_cli.py` to:
  * align week IDs to the exchange time zone (`EXCHANGE_TZ`).
  * report break percentages for London, New York, Asia **and** the new overlap session.
  * print explicit week lists for every criterion.
* **Performance** – Removed expensive per‑week tick scans; all statistics now leverage the session‑level summaries.
* **Schema unchanged** – Only the `Sessions` value set grows (no column changes). Existing downstream scripts remain compatible. 