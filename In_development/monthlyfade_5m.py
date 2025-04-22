#!/usr/bin/env python3
"""
monthly_open_5m_fade_loose.py
Loosened filters so trades can flow; diagnostics show rejection reason.
"""

from __future__ import annotations
import sqlite3, pandas as pd, numpy as np
from datetime import timedelta
from pathlib import Path

BAR_MINUTES      = 5
TOL_TICKS        = 15
DRIFT_BARS       = 2        # << was 3
OFI_TOP_PCT      = 0.50     # << was 0.35
DELTA_FLIP_SEC   = 0        # << disable flip filter
STOP_ASR_FACTOR  = 0.6
TARGET_ASR_MULT  = 2.0
FEE_TICKS        = 4
DB_FILE          = Path("crypto_data.db")


def resample_1s(df):
    bar = (df.resample(f"{BAR_MINUTES}T", on="ts")
             .agg({"Last":["first","max","min","last"],
                   "BidVolume":"sum","AskVolume":"sum","Volume":"sum"}))
    bar.columns = ["Open","High","Low","Close","BidVol","AskVol","Vol"]
    bar.dropna(subset=["Open"], inplace=True)
    bar["ofi"] = bar["BidVol"] - bar["AskVol"]
    return bar


def load():
    conn = sqlite3.connect(DB_FILE)
    sess = pd.read_sql("""SELECT SessionStart, SessionEnd, SessionOpen,
                                 SessionASR
                          FROM session_summary ORDER BY SessionStart""",
                       conn, parse_dates=["SessionStart","SessionEnd"])
    sess["SessionStart"] = sess["SessionStart"].dt.tz_localize("UTC")
    sess["SessionEnd"]   = sess["SessionEnd"].dt.tz_localize("UTC")
    sess["ASR30"]        = sess["SessionASR"].rolling(30, min_periods=1).mean()

    key = pd.read_sql("""SELECT SessionStartUTC, MonthlyOpen
                         FROM btc_key_levels ORDER BY SessionStartUTC""",
                      conn, parse_dates=["SessionStartUTC"])
    key["SessionStartUTC"] = key["SessionStartUTC"].dt.tz_localize("UTC")

    ticks = pd.read_parquet("ticks.parquet")
    ticks["ts"] = pd.to_datetime(ticks["ts"], utc=True)
    ticks.sort_values("ts", inplace=True)
    conn.close()
    return sess, key, ticks


def backtest():
    sess, key, ticks = load()
    sess = pd.merge_asof(sess, key, left_on="SessionStart",
                         right_on="SessionStartUTC", direction="backward")

    bars_all = resample_1s(ticks)
    ofi_thresh = bars_all["ofi"].abs().quantile(1 - OFI_TOP_PCT)

    trades, rejects = [], []

    for s in sess.itertuples():
        level = s.MonthlyOpen
        if pd.isna(level): continue
        bars = bars_all[s.SessionStart:s.SessionEnd]
        if bars.empty: continue

        direction = 1 if level > s.SessionOpen else -1
        touches = bars[abs(bars["Close"] - level) <= TOL_TICKS]
        if touches.empty:
            rejects.append(("no_touch", s.SessionStart)); continue

        idx = touches.index[0]
        i   = bars.index.get_loc(idx)
        if i < DRIFT_BARS:
            rejects.append(("drift_window", idx)); continue

        drift_slice = bars.iloc[i-DRIFT_BARS:i]
        drift_ok = (direction==1 and drift_slice["Low"].is_monotonic_increasing) or \
                   (direction==-1 and drift_slice["High"].is_monotonic_decreasing)
        if not drift_ok:
            rejects.append(("drift_fail", idx)); continue

        if abs(bars.loc[idx,"ofi"]) < ofi_thresh:
            rejects.append(("ofi_fail", idx)); continue

        # passed filters → trade
        entry = bars.loc[idx,"Close"]
        stop  = level + direction*STOP_ASR_FACTOR*s.ASR30
        tgt   = entry - direction*TARGET_ASR_MULT*s.ASR30

        exit_px=exit_ts=reason=None
        for row in bars.iloc[i+1:].itertuples():
            p=row.Close
            if (direction==1 and p>=stop) or (direction==-1 and p<=stop):
                exit_px,exit_ts,reason=stop,row.Index,"stop";break
            if (direction==1 and p<=tgt) or (direction==-1 and p>=tgt):
                exit_px,exit_ts,reason=p,row.Index,"target";break
        if exit_px is None:
            exit_px,exit_ts,reason = bars.iloc[-1]["Close"],bars.index[-1],"session_end"

        pnl = (exit_px-entry)*(-direction)-FEE_TICKS
        trades.append(dict(entry_ts=idx,exit_ts=exit_ts,entry=entry,
                           exit=exit_px,pnl_ticks=pnl,reason=reason))

    # ---------- report ----------
    rej_df = pd.DataFrame(rejects, columns=["why","ts"])
    print("\nReject summary\n", rej_df["why"].value_counts(dropna=False))
    print("Trades taken :", len(trades))
    if not trades: return
    df = pd.DataFrame(trades)
    stop_ticks = STOP_ASR_FACTOR * sess["ASR30"].mean() / 0.1
    df["net_R"] = df["pnl_ticks"]/stop_ticks
    print(f"Hit‑rate     : {(df['net_R']>0).mean():.1%}")
    print(f"Avg net R    : {df['net_R'].mean():.2f}")
    df.to_csv("monthly_open_5m_trades.csv", index=False)
    print("Saved monthly_open_5m_trades.csv")


if __name__ == "__main__":
    backtest()
