#!/usr/bin/env python3
"""
micro_window.py  –  tick‑level enrichment for PoC touches
(boole‑mask slice version: no more KeyError)
"""

from __future__ import annotations
import argparse, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

COLS = ["ts","Open","High","Low","Last",
        "Volume","NumberOfTrades","BidVolume","AskVolume"]
CACHE_PARQUET = Path("ticks.parquet")

# ---------------------------------------------------------------------------
def load_ticks(txt: Path) -> pd.DataFrame:
    if CACHE_PARQUET.exists():
        return pd.read_parquet(CACHE_PARQUET)

    try:
        df = pd.read_csv(txt, parse_dates=["Timestamp"])
        df.rename(columns={"Timestamp": "ts"}, inplace=True)
    except ValueError:
        df = pd.read_csv(txt, names=COLS, parse_dates=["ts"])

    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df.to_parquet(CACHE_PARQUET, index=False)
    print(f"Cached ticks → {CACHE_PARQUET} ({len(df):,} rows)")
    return df

# ---------------------------------------------------------------------------
def calc_ofi(g: pd.DataFrame) -> pd.Series:
    return g["BidVolume"].diff().fillna(0) - g["AskVolume"].diff().fillna(0)

# ---------------------------------------------------------------------------
def enrich(db: Path, ticks_path: Path, window: int):
    conn = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM poc_revisits WHERE revisited = 1", conn,
                     parse_dates=["origin_session_start","revisit_session_start"])
    for col in ("origin_session_start","revisit_session_start"):
        df[col] = pd.to_datetime(df[col], utc=True)

    ticks = (load_ticks(ticks_path)
             .set_index("ts")
             .sort_index())                # still useful for speed

    win = timedelta(seconds=window)
    metrics = []

    for r in df.itertuples():
        t = r.revisit_session_start
        mask = (ticks.index >= t - win) & (ticks.index <= t + win)
        slc  = ticks.loc[mask]

        if slc.empty:
            metrics.append((None, None, None))
            continue

        res = slc.resample("1S").agg({
            "BidVolume": "max",
            "AskVolume": "max",
            "Last": "last"})
        res["ofi"] = calc_ofi(res)

        max_ofi      = res["ofi"].abs().max()
        max_tick_exc = slc["Last"].diff().abs().max()
        post         = res.loc[t:t + timedelta(seconds=30), "ofi"].cumsum()
        flip         = bool(len(post) >= 2 and (post.iloc[0] > 0) != (post.iloc[-1] > 0))

        metrics.append((max_ofi, max_tick_exc, flip))

    df[["max_ofi_1s", "max_tick_exc", "delta_flip"]] = metrics
    df.to_sql("poc_revisits_micro", conn, if_exists="replace", index=False)
    conn.close()
    print(f"Written {len(df):,} rows → poc_revisits_micro")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Enrich PoC touches with tick‑level OFI / excursion metrics")
    p.add_argument("--db",    type=Path, default="crypto_data.db")
    p.add_argument("--ticks", type=Path, required=True)
    p.add_argument("--window", type=int, default=300,
                   help="Seconds before & after touch to examine")
    args = p.parse_args()
    enrich(args.db, args.ticks, args.window)
