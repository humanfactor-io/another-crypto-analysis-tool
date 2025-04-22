#!/usr/bin/env python3
"""
key_open_fade_backtest.py  ─  2025‑04 tuned edition
====================================================
Mean‑reversion fade when BTC drifts into a **Weekly / Monthly / Quarterly**
OPEN level.  Per‑level stops & targets are now configurable.

• reads   : crypto_data.db   (session_summary, btc_key_levels)
• reads   : ticks.parquet    (built once by micro_window.py)
• writes  : key_open_trades.csv  (full trade log)

Edit the PARAMETER BLOCK, run → review diagnostics / summary.
"""

from __future__ import annotations
import sqlite3, pandas as pd
from datetime import timedelta
from pathlib import Path

# ════════════════════════════════════════════════════════════════════════════
# PARAMETER BLOCK – tweak & re‑run
# ════════════════════════════════════════════════════════════════════════════
TOL_TICKS      = 15      # proximity that defines “touch”
DRIFT_MINUTES  = 3       # look‑back drift filter (0 → disable)
OFI_SIGMA_NEG  = -0.5    # require 60‑sec OFI < –0.5 σ (≥0 disables)
HOLD_HOURS     = 2       # hard timeout

# Per‑level stops (ticks) & target factors (percentage of entry→VWAP distance)
# ORIGINAL: STOP_MAP   = dict(MonthlyOpen=24, WeeklyOpen=36, QuarterlyOpen=36)
# ORIGINAL: TARGET_MAP = dict(MonthlyOpen=0.7, WeeklyOpen=0.4, QuarterlyOpen=0.4)

STOP_MAP   = dict(MonthlyOpen=26, WeeklyOpen=25, QuarterlyOpen=25)
TARGET_MAP = dict(MonthlyOpen=3.0, WeeklyOpen=0.5, QuarterlyOpen=0.5)

ACTIVE_LEVELS = list(STOP_MAP.keys())    # levels to trade
DB_FILE       = Path("crypto_data.db")
# ════════════════════════════════════════════════════════════════════════════


def load_db():
    conn = sqlite3.connect(DB_FILE)
    sess = pd.read_sql("SELECT * FROM session_summary", conn,
                       parse_dates=["SessionStart", "SessionEnd"])
    sess["SessionStart"] = pd.to_datetime(sess["SessionStart"], utc=True)
    sess["SessionEnd"]   = pd.to_datetime(sess["SessionEnd"],   utc=True)

    key = pd.read_sql("""SELECT SessionStartUTC, WeeklyOpen, MonthlyOpen,
                                QuarterlyOpen
                         FROM btc_key_levels
                         ORDER BY SessionStartUTC""",
                      conn, parse_dates=["SessionStartUTC"])
    key["SessionStartUTC"] = pd.to_datetime(key["SessionStartUTC"], utc=True)

    ticks = pd.read_parquet("ticks.parquet")
    ticks["ts"] = pd.to_datetime(ticks["ts"], utc=True)
    ticks.sort_values("ts", inplace=True)

    conn.close()
    return sess, key, ticks


def resample_ofi(df: pd.DataFrame) -> pd.Series:
    rs = (df.resample("1S", on="ts")
            .agg({"BidVolume": "sum", "AskVolume": "sum"})
            .fillna(0))
    rs["ofi"] = rs["BidVolume"].diff().fillna(0) - rs["AskVolume"].diff().fillna(0)
    return rs["ofi"].rolling("60s").sum()


def backtest():
    sess_df, key_df, ticks = load_db()

    # attach most recent key‑open row to each session
    sess_df = pd.merge_asof(sess_df.sort_values("SessionStart"),
                            key_df.sort_values("SessionStartUTC"),
                            left_on="SessionStart", right_on="SessionStartUTC",
                            direction="backward")

    trades, diag = [], dict(no_touch=0, drift=0, ofi=0)

    for s in sess_df.itertuples():
        intra = ticks[(ticks["ts"] >= s.SessionStart) & (ticks["ts"] <= s.SessionEnd)]
        if intra.empty:
            continue

        ofi_60 = resample_ofi(intra)
        ofi_sigma = ofi_60.std(skipna=True) or 1.0

        for lvl_name in ACTIVE_LEVELS:
            level = getattr(s, lvl_name)
            if pd.isna(level):
                continue

            direction = 1 if level > s.SessionOpen else -1

            # 1) first touch within tolerance
            touches = intra[abs(intra["Last"] - level) <= TOL_TICKS]
            if touches.empty:
                diag["no_touch"] += 1
                continue
            t_touch = touches.iloc[0]["ts"]
            entry_px = touches.iloc[0]["Last"]

            # 2) drift filter ---------------------------------------------
            if DRIFT_MINUTES:
                lookback = intra[(intra["ts"] >= t_touch - timedelta(minutes=DRIFT_MINUTES))
                                 & (intra["ts"] <  t_touch)]
                if lookback.empty:
                    diag["drift"] += 1; continue
                drift_ok = ((direction==1 and lookback["Last"].iloc[-1] > lookback["Last"].iloc[0]) or
                            (direction==-1 and lookback["Last"].iloc[-1] < lookback["Last"].iloc[0]))
                if not drift_ok:
                    diag["drift"] += 1; continue

            # 3) OFI filter -----------------------------------------------
            if OFI_SIGMA_NEG < 0:
                ofi_val = ofi_60.reindex([t_touch.floor("S")], method="nearest").iloc[0]
                if direction * ofi_val > OFI_SIGMA_NEG * abs(ofi_sigma):
                    diag["ofi"] += 1; continue

            # 4) trade management -----------------------------------------
            stop_px   = level + direction * STOP_MAP[lvl_name]
            expire_ts = t_touch + timedelta(hours=HOLD_HOURS)

            sub = intra[intra["ts"] >= t_touch]
            vwap = (sub["Last"] * sub["Volume"]).cumsum() / sub["Volume"].cumsum()

            exit_px = exit_ts = exit_reason = None

            for i, row in enumerate(sub.itertuples()):
                price = row.Last
                if i == 0:  # skip entry tick
                    continue

                # stop
                if (direction==1 and price >= stop_px) or (direction==-1 and price <= stop_px):
                    exit_px, exit_ts, exit_reason = stop_px, row.ts, "stop"; break

                # dynamic half‑VWAP target
                dist_vwap = abs(entry_px - vwap.loc[row.Index])
                target_px = entry_px - direction * TARGET_MAP[lvl_name] * dist_vwap
                if (direction==1 and price <= target_px) or (direction==-1 and price >= target_px):
                    exit_px, exit_ts, exit_reason = price, row.ts, "target"; break

                # timeout
                if row.ts >= expire_ts:
                    exit_px, exit_ts, exit_reason = price, row.ts, "timeout"; break

            if exit_px is None:  # fallback at session end
                exit_px, exit_ts, exit_reason = sub.iloc[-1]["Last"], sub.iloc[-1]["ts"], "session_end"

            pnl_ticks = (exit_px - entry_px) * (-direction)

            trades.append(dict(key=lvl_name, entry_ts=t_touch, exit_ts=exit_ts,
                               reason=exit_reason, entry=entry_px, exit=exit_px,
                               pnl_ticks=pnl_ticks))

    # ── REPORTS ────────────────────────────────────────────────────────────
    print("\nFilter diagnostics")
    for k, v in diag.items():
        print(f"{k:<12}: {v}")
    print(f"trades        : {len(trades)}")

    if not trades:
        print("No trades – tweak parameters.")
        return

    df = pd.DataFrame(trades)
    summary = (df.groupby("key")["pnl_ticks"]
                 .agg(trades="size",
                      hit_rate=lambda x: (x>0).mean(),
                      avg_R="mean")
                 .round(2))

    print("\nBack‑test summary (fade into key‑opens)\n")
    print(summary.to_string())

    df.to_csv("key_open_trades.csv", index=False)
    print("\nTrade log saved → key_open_trades.csv")


if __name__ == "__main__":
    backtest()
