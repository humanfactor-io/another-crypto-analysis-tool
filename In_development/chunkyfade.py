#!/usr/bin/env python3
"""
monthly_open_chunky_fade.py
────────────────────────────────────────────────────────────────────────────
Fade the first *calm* drift into the **Monthly Open** and hold for a full
mean‑reversion to the session VWAP ± 1 × ASR(30).

Filters
-------
• Price drifts ≥ 15 min *toward* the level
• 1‑sec OFI on touch is in the **top 25 %** absolute readings
• 30‑sec cumulative OFI flips sign after the touch  (absorption)
• Only the *first* qualifying touch per session is traded

Trade management
----------------
• Stop    = 0.6 × ASR(30)   (≈ $900 today)
• Target  = 1.0 × ASR(30)   (≈ $1.6 k) toward VWAP
• Hard timeout = 6 h
• Fixed friction = 4 ticks (= $0.40 per BTC) deducted from every trade

Outputs
-------
• Prints diagnostics & per‑trade stats
• Saves full log to **monthly_open_trades.csv**
"""

from __future__ import annotations
import sqlite3, pandas as pd, numpy as np
from datetime import timedelta
from pathlib import Path

# ════════════════════════════════════════════════════════════════════════
# USER‑TUNABLE PARAMS
# ════════════════════════════════════════════════════════════════════════
TOL_TICKS      = 15      # touch window
DRIFT_MINUTES  = 15      # calm grind
OFI_TOP_PCT    = 0.25    # OFI must be in top 25 %
DELTA_FLIP_SEC = 30      # absorption window
STOP_ASR       = 0.6     # stop = 0.6 × ASR30
TARGET_ASR     = 2.5     # TP   = 1.0 × ASR30
HOLD_HOURS     = 6       # max holding time
FEE_TICKS      = 4       # fees/slippage
DB_FILE        = Path("crypto_data.db")
# ════════════════════════════════════════════════════════════════════════


# ── data helpers --------------------------------------------------------
def load_data():
    conn = sqlite3.connect(DB_FILE)

    sess = pd.read_sql("""SELECT SessionStart, SessionEnd, SessionOpen,
                                 SessionASR
                          FROM session_summary
                          ORDER BY SessionStart""",
                       conn, parse_dates=["SessionStart", "SessionEnd"])
    sess["SessionStart"] = sess["SessionStart"].dt.tz_localize("UTC")
    sess["SessionEnd"]   = sess["SessionEnd"].dt.tz_localize("UTC")
    sess["ASR30"]        = sess["SessionASR"].rolling(30, min_periods=1).mean()

    key = pd.read_sql("""SELECT SessionStartUTC, MonthlyOpen, WeeklyOpen,
                                QuarterlyOpen
                         FROM btc_key_levels ORDER BY SessionStartUTC""",
                      conn, parse_dates=["SessionStartUTC"])
    key["SessionStartUTC"] = key["SessionStartUTC"].dt.tz_localize("UTC")

    ticks = pd.read_parquet("ticks.parquet")
    ticks["ts"] = pd.to_datetime(ticks["ts"], utc=True)
    ticks.sort_values("ts", inplace=True)

    conn.close()
    return sess, key, ticks


def resample_1s(df: pd.DataFrame) -> pd.DataFrame:
    rs = (df.resample("1S", on="ts")
            .agg({"BidVolume": "sum",
                  "AskVolume": "sum",
                  "Last": "last"})
            .fillna(method="ffill"))
    rs["ofi"] = rs["BidVolume"].diff().fillna(0) - rs["AskVolume"].diff().fillna(0)
    return rs


def delta_flip(series: pd.Series) -> bool:
    """True if 30‑sec cumulative OFI flips sign."""
    if series.empty: return False
    cum = series.cumsum()
    return len(cum) >= 2 and np.sign(cum.iloc[0]) != np.sign(cum.iloc[-1])


# ── main back‑test ------------------------------------------------------
def backtest():
    sess, key, ticks = load_data()

    # merge MonthlyOpen into every session row
    sess = pd.merge_asof(sess.sort_values("SessionStart"),
                         key.sort_values("SessionStartUTC"),
                         left_on="SessionStart", right_on="SessionStartUTC",
                         direction="backward")

    # global OFI threshold (top 25 % absolute)
    ofi_thresh = resample_1s(ticks)["ofi"].abs().quantile(1 - OFI_TOP_PCT)

    trades, rej = [], dict(no_touch=0, filters=0)

    for s in sess.itertuples():
        level = s.MonthlyOpen
        if pd.isna(level): continue

        intra = ticks[(ticks["ts"] >= s.SessionStart) &
                      (ticks["ts"] <= s.SessionEnd)]
        if intra.empty: continue

        sec = resample_1s(intra)

        direction = 1 if level > s.SessionOpen else -1
        touches = intra[abs(intra["Last"] - level) <= TOL_TICKS]
        if touches.empty:
            rej["no_touch"] += 1; continue

        # ---- first qualifying touch only
        t_touch = touches.iloc[0]["ts"]
        entry   = touches.iloc[0]["Last"]

        # drift filter
        lb = intra[(intra["ts"] >= t_touch - timedelta(minutes=DRIFT_MINUTES)) &
                   (intra["ts"] <  t_touch)]
        drift_ok = lb.size and (
            (direction==1 and lb["Last"].iloc[-1] > lb["Last"].iloc[0]) or
            (direction==-1 and lb["Last"].iloc[-1] < lb["Last"].iloc[0]))
        if not drift_ok:
            rej["filters"] += 1; continue

        # OFI
        ofi_val = sec.loc[t_touch.floor("S"), "ofi"]
        if abs(ofi_val) < ofi_thresh:
            rej["filters"] += 1; continue

        # delta‑flip
        if not delta_flip(sec.loc[t_touch.floor("S"):
                                  t_touch + timedelta(seconds=DELTA_FLIP_SEC), "ofi"]):
            rej["filters"] += 1; continue

        # ---- trade management -----------------------------------------
        stop_px   = level + direction * STOP_ASR * s.ASR30
        target_px = entry  - direction * TARGET_ASR * s.ASR30
        expire_ts = t_touch + timedelta(hours=HOLD_HOURS)

        sub   = intra[intra["ts"] >= t_touch]
        exit_px = exit_ts = reason = None

        for row in sub.itertuples():
            p = row.Last
            if (direction==1 and p >= stop_px) or (direction==-1 and p <= stop_px):
                exit_px, exit_ts, reason = stop_px, row.ts, "stop"; break
            crossed = (direction==1 and p <= target_px) or (direction==-1 and p >= target_px)
            if crossed:
                exit_px, exit_ts, reason = p, row.ts, "target"; break
            if row.ts >= expire_ts:
                exit_px, exit_ts, reason = p, row.ts, "timeout"; break

        if exit_px is None:  # safety
            exit_px, exit_ts, reason = sub.iloc[-1]["Last"], sub.iloc[-1]["ts"], "session_end"

        pnl_raw = (exit_px - entry) * (-direction)
        pnl_net = pnl_raw - FEE_TICKS

        trades.append(dict(entry_ts=t_touch, exit_ts=exit_ts, reason=reason,
                           entry=entry, exit=exit_px,
                           pnl_raw=pnl_raw, pnl_net=pnl_net))

    # ---- results ------------------------------------------------------
    print("\nRejections  :", rej)
    print("Trades taken:", len(trades))
    if not trades: return

    df = pd.DataFrame(trades)
    expectancy = df["pnl_net"].mean()
    hitrate    = (df["pnl_net"] > 0).mean()
    print(f"\nMonthly‑Open chunky fade")
    print(f"Hit‑rate   : {hitrate:.2%}")
    print(f"Avg net R  : {expectancy:.2f} ticks (after {FEE_TICKS} tick fees)")
    df.to_csv("monthly_open_trades.csv", index=False)
    print("\nTrade log saved → monthly_open_trades.csv")


if __name__ == "__main__":
    backtest()
