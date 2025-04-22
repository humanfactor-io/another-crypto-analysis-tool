#!/usr/bin/env python3
"""
monday_rotation_backtest_mid.py
────────────────────────────────────────────────────────────────────────
Fade breakout of Monday range back into value with two profit targets:

  • TP‑1 → Monday‑Mid (close ½, move stop to entry)
  • TP‑2 → opposite Monday extreme (full rotation)

Exit reasons stored in rotation_trades:

    stop          – initial/trailed stop hit
    target_mid    – hit Mid only, runner later timed/stopped
    target_full   – full rotation reached
    atr_timer     – ATR‑based low‑vol exit (≥ MIN_HOLD_HRS)
    timer24h      – hard 24 h cut‑off

Run:

    python monday_rotation_backtest_mid.py \
        --db    crypto_data.db \
        --ticks BTCUSDT_PERP_BINANCE_normalized.txt
"""
from __future__ import annotations
import argparse, sqlite3, math, datetime, sys
from pathlib import Path
from dataclasses import dataclass, asdict
import pandas as pd

# ── user‑tunable params ──────────────────────────────────────────────
TOL_TICKS      = 15        # breakout tolerance
STOP_PCT       = 0.30      # stop = 30 % MondayRange
ATR_WINDOW_MIN = 30        # ATR window (minutes)
ATR_THRESH_PCT = 0.15      # ATR exit when ATR < 15 % MondayRange
MIN_HOLD_HRS   = 4         # cannot ATR‑exit before 4 h
HARD_TIMER_HRS = 24        # absolute max hold
HALF_CLOSE_PCT = 0.50      # portion closed at Monday‑Mid
# --------------------------------------------------------------------

@dataclass(slots=True)
class Trade:
    entry_ts:   pd.Timestamp
    exit_ts:    pd.Timestamp
    entry:      float
    exit:       float
    direction:  int            # +1 long, –1 short
    stop_ticks: int
    reason:     str
    net_R:      float

# ── helpers ----------------------------------------------------------
def atr_slice(series: pd.Series) -> float:
    """High‑low range of the slice."""
    return (series.max() - series.min()) if not series.empty else 0.0

def load_key_levels(conn) -> pd.DataFrame:
    q = ("SELECT SessionStartUTC, MondayHigh, MondayLow "
         "FROM btc_key_levels WHERE MondayHigh IS NOT NULL")
    df = pd.read_sql(q, conn, parse_dates=["SessionStartUTC"])
    df["SessionStartUTC"] = df["SessionStartUTC"].dt.tz_localize(None)
    df["MondayMid"] = (df["MondayHigh"] + df["MondayLow"]) / 2
    return df

def slice_ticks(csv: Path,
                start_ts: datetime.datetime,
                end_ts:   datetime.datetime) -> pd.Series:
    """Return tick Last prices between start_ts and end_ts."""
    names = ["ts","Open","High","Low","Last","Volume",
             "Trades","BidVol","AskVol"]

    df = pd.read_csv(csv,
                     names=names,
                     header=None,
                     parse_dates=["ts"],
                     low_memory=False)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df.dropna(subset=["ts"], inplace=True)

    df = df[(df["ts"] >= start_ts) & (df["ts"] <= end_ts)]
    df.set_index("ts", inplace=True)
    df.sort_index(inplace=True)
    return df["Last"]

# ── main back‑test ---------------------------------------------------
def backtest(db: Path, tick_file: Path) -> None:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row             # dict‑style rows
    levels = load_key_levels(conn)

    trades: list[Trade] = []
    rows = conn.execute(
        "SELECT * FROM session_summary WHERE Sessions='NewYork'"
    ).fetchall()

    for row in rows:
        sess_start = pd.to_datetime(row["SessionStart"]).tz_localize(None)
        week_no    = sess_start.isocalendar().week

        wk = levels[levels["SessionStartUTC"]
                    .dt.isocalendar().week == week_no]
        if wk.empty: continue
        monday_high, monday_low, monday_mid = \
            wk.iloc[0][["MondayHigh","MondayLow","MondayMid"]]
        monday_range = monday_high - monday_low
        if monday_range == 0 or pd.isna(monday_range): continue

        # determine breakout direction
        direction = 0
        if row["SessionHigh"] > monday_high + TOL_TICKS:
            direction = -1   # short fade
        elif row["SessionLow"] < monday_low - TOL_TICKS:
            direction = +1   # long fade
        if direction == 0: continue

        entry_px = row["SessionClose"]
        stop_px  = entry_px - direction * STOP_PCT * monday_range
        risk     = abs(entry_px - stop_px)
        stop_ticks = int(risk / 0.10)

        # load tick path (max 24 h)
        start_ts, end_ts = sess_start, sess_start + datetime.timedelta(hours=HARD_TIMER_HRS)
        ticks = slice_ticks(tick_file, start_ts, end_ts)

        hit_mid = False
        exit_reason, exit_px, exit_ts = "timer24h", ticks.iloc[-1], ticks.index[-1]

        for ts, px in ticks.items():
            elapsed = (ts - start_ts).total_seconds() / 3600

            # stop
            if (direction==1 and px <= stop_px) or (direction==-1 and px >= stop_px):
                exit_reason, exit_px, exit_ts = "stop", px, ts
                break

            # full rotation TP‑2
            if (direction==1 and px <= monday_low) or (direction==-1 and px >= monday_high):
                exit_reason, exit_px, exit_ts = "target_full", px, ts
                break

            # TP‑1 Monday‑Mid
            if not hit_mid and (
               (direction==1 and px <= monday_mid) or
               (direction==-1 and px >= monday_mid)):
                hit_mid = True
                stop_px = entry_px  # move stop to break‑even

            # ATR timer after minimum hold
            if elapsed >= MIN_HOLD_HRS:
                atr_now = atr_slice(ticks.loc[ts - datetime.timedelta(
                                            minutes=ATR_WINDOW_MIN):ts])
                if atr_now < ATR_THRESH_PCT * monday_range:
                    exit_reason, exit_px, exit_ts = "atr_timer", px, ts
                    break

        # calculate R
        pnl = (exit_px - entry_px) * direction
        if exit_reason == "target_full":
            net_R = pnl / risk
        elif exit_reason in ("atr_timer", "timer24h", "stop"):
            size_factor = HALF_CLOSE_PCT if hit_mid else 1.0
            net_R = size_factor * pnl / risk
            if exit_reason == "atr_timer" and hit_mid and pnl == 0:
                exit_reason = "target_mid"
        else:
            net_R = pnl / risk  # fallback

        trades.append(Trade(sess_start, exit_ts, entry_px, exit_px,
                            direction, stop_ticks, exit_reason,
                            round(net_R, 2)))

    # write results
    df = pd.DataFrame(asdict(t) for t in trades)
    df.to_sql("rotation_trades", conn, if_exists="replace", index=False)
    print(f"Saved {len(df)} trades → rotation_trades")
    conn.close()

# ── CLI --------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",    type=Path, default="crypto_data.db")
    ap.add_argument("--ticks", type=Path,
                    default="BTCUSDT_PERP_BINANCE_normalized.txt")
    args = ap.parse_args()

    if not args.db.exists() or not args.ticks.exists():
        sys.exit("DB or tick file not found.")
    backtest(args.db, args.ticks)
