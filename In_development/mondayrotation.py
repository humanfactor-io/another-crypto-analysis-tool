#!/usr/bin/env python3
"""
monday_rotation_backtest.py   •   v3.2
────────────────────────────────────────────────────────────────────────────
NY‑session Monday‑Range Rotation back‑test
• dynamic Monday‑range filters
• breakout candle filter
• stop 0.3× range, BE trail after Monday‑Mid
• 12‑hour timer exit
• saves trades to SQLite table  rotation_trades  in crypto_data.db
"""

from __future__ import annotations
import sqlite3, pandas as pd
from datetime import timedelta
from pathlib import Path

# ── PARAMETERS ─────────────────────────────────────────────────────────
BAR_MIN = 30
BUFFER_TICKS = 25
STOP_FACTOR = 0.3          # stop size
TARGET_MULT = 1.2          # full rotation
SCALE_OUT_MID = True       # 50 % + BE trail
MAX_HOURS = 12             # timer
FEE_TICKS = 4

MIN_RANGE_USD     = 1_200
MIN_RANGE_PCT_ADR = 0.50
MIN_TARGET_DIST   = 1_100
BREAK_BAR_FRAC    = 0.35

DB_FILE   = Path("crypto_data.db")
ROT_TABLE = "rotation_trades"
TICKVALUE = 0.10            # 1 tick = $0.10 per BTC
# ───────────────────────────────────────────────────────────────────────

def utc_to_session(ts):
    return "Asia" if ts.hour < 7 else "London" if ts.hour < 15 else "NewYork"

def resample_bars(ticks: pd.DataFrame) -> pd.DataFrame:
    return (ticks
            .resample(f"{BAR_MIN}T", on="ts")
            .agg(Open=('Last', 'first'),
                 High=('Last', 'max'),
                 Low=('Last', 'min'),
                 Close=('Last', 'last'))
            .dropna(subset=["Open"]))

# ── DATA LOADERS ──────────────────────────────────────────────────────
def load():
    conn = sqlite3.connect(DB_FILE)

    key = pd.read_sql("""SELECT SessionStartUTC, MondayHigh, MondayLow, MondayMid
                         FROM btc_key_levels
                         WHERE MondayHigh IS NOT NULL
                         ORDER BY SessionStartUTC""",
                      conn, parse_dates=["SessionStartUTC"])
    key["SessionStartUTC"] = key["SessionStartUTC"].dt.tz_localize("UTC")

    day = pd.read_sql("""SELECT Date,
                                MAX(SessionHigh) AS High,
                                MIN(SessionLow)  AS Low
                         FROM session_summary
                         GROUP BY Date
                         ORDER BY Date""",
                      conn, parse_dates=["Date"])
    day["ADR"] = day["High"] - day["Low"]
    day.set_index("Date", inplace=True)

    ticks = pd.read_parquet("ticks.parquet")
    ticks["ts"] = pd.to_datetime(ticks["ts"], utc=True)
    ticks.sort_values("ts", inplace=True)
    conn.close()
    return key, ticks, day

def adr30_before(ts, day_df):
    cutoff = ts.tz_convert(None).normalize()
    return day_df[day_df.index < cutoff]["ADR"].tail(30).mean()

# ── DB SAVE ───────────────────────────────────────────────────────────
def save_trades_to_db(df: pd.DataFrame, table=ROT_TABLE):
    conn = sqlite3.connect(DB_FILE)
    df.to_sql(table, conn, if_exists="replace", index=False)
    conn.close()
    print(f"Saved {len(df)} trades → table '{table}' in {DB_FILE}")

# ── BACK‑TEST ─────────────────────────────────────────────────────────
def backtest():
    key, ticks, day = load()
    bars_all = resample_bars(ticks)
    trades = []

    for wk in key.itertuples(index=False):
        hi, lo, mid = wk.MondayHigh, wk.MondayLow, wk.MondayMid
        rng = hi - lo
        # range / quality filters
        if rng < MIN_RANGE_USD: continue
        if rng < MIN_TARGET_DIST / TARGET_MULT: continue
        if rng < MIN_RANGE_PCT_ADR * adr30_before(wk.SessionStartUTC, day): continue

        stop_ticks = STOP_FACTOR * rng / TICKVALUE
        tue_open = wk.SessionStartUTC + timedelta(days=1)
        week_end = wk.SessionStartUTC + timedelta(days=5)
        bars = bars_all[tue_open:week_end]

        direction = None
        entry_row = None
        # scan bars
        for prev, curr in zip(bars.iloc[:-1].itertuples(), bars.iloc[1:].itertuples()):
            inside_prev = lo - BUFFER_TICKS <= prev.Close <= hi + BUFFER_TICKS
            big = (curr.High - curr.Low) >= BREAK_BAR_FRAC * rng
            if direction is None:
                if inside_prev and curr.Close > hi + BUFFER_TICKS and big:
                    direction = -1; continue
                if inside_prev and curr.Close < lo - BUFFER_TICKS and big:
                    direction = +1; continue
            else:
                if lo + BUFFER_TICKS <= curr.Close <= hi - BUFFER_TICKS:
                    entry_row = curr; break
        if entry_row is None or utc_to_session(entry_row.Index) != "NewYork":
            continue

        entry_ts, entry_px = entry_row.Index, entry_row.Close
        stop_px = entry_px - direction * STOP_FACTOR * rng
        tgt_mid = mid
        tgt_full = lo if direction == -1 else hi
        expire_ts = entry_ts + timedelta(hours=MAX_HOURS)

        scaled = False
        for r in bars[entry_ts:].itertuples():
            price = r.Close
            if (direction == -1 and price >= stop_px) or (direction == +1 and price <= stop_px):
                exit_px, exit_ts, reason = stop_px, r.Index, "stop"; break
            if SCALE_OUT_MID and not scaled:
                hit_mid = (direction == -1 and price <= tgt_mid) or (direction == +1 and price >= tgt_mid)
                if hit_mid:
                    scaled = True
                    stop_px = entry_px  # trail to B/E
                    continue
            if (direction == -1 and price <= tgt_full) or (direction == +1 and price >= tgt_full):
                exit_px, exit_ts, reason = price, r.Index, "target"; break
            if r.Index >= expire_ts:
                exit_px, exit_ts, reason = price, r.Index, "timer"; break
        else:
            exit_px, exit_ts, reason = bars.iloc[-1].Close, bars.index[-1], "week_end"

        pnl_ticks = (exit_px - entry_px) * direction / TICKVALUE - FEE_TICKS
        trades.append(dict(entry_ts=entry_ts, exit_ts=exit_ts,
                           entry=entry_px, exit=exit_px,
                           direction=direction, reason=reason,
                           pnl_ticks=pnl_ticks, stop_ticks=stop_ticks))

    if not trades:
        print("No trades."); return
    df = pd.DataFrame(trades)
    df["net_R"] = df["pnl_ticks"] / df["stop_ticks"]
    print(f"Trades:{len(df)}  Hit:{(df.net_R>0).mean():.1%}  Avg R:{df.net_R.mean():.2f}")
    save_trades_to_db(df)

if __name__ == "__main__":
    backtest()
