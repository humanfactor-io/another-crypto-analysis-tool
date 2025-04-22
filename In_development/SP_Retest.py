#!/usr/bin/env python3
"""
Single‑Print Reaction back‑test
--------------------------------
Scans `session_summary` for sessions flagged SinglePrints = 1, then
simulates fades on the first revisit of the single‑print edge in the
next N sessions.
"""

import sqlite3, pandas as pd, numpy as np, argparse, os, datetime as dt

# ─── USER PARAMETERS ────────────────────────────────────────────────────
DB_FILE         = "crypto_data.db"
N_LOOKAHEAD     = 3          # sessions after signal we allow entry
ENTRY_PAD_TICKS = 1
SL_PAD_TICKS    = 2
TP1_R           = 1.0
TP2_R           = 2.0
BE_AFTER_MIN    = 60         # move stop to BE after 60 min in favour
TICK_SIZE       = 0.1
QUAL_SESSIONS   = {"Asia","London","NewYork"}  # where we allow entries
# ────────────────────────────────────────────────────────────────────────

def load_sessions(conn):
    q = """
    SELECT *, strftime('%Y‑%m‑%d %H:%M:%S',SessionStart) AS ts
    FROM session_summary
    ORDER BY SessionStart
    """
    df = pd.read_sql(q, conn, parse_dates=["SessionStart","SessionEnd"])
    # mark calendar sequence
    df["idx"] = np.arange(len(df))
    return df

def first_touch(prices, level, pad, side):
    """Return first index where price touches (<= / >=) level±pad."""
    if side == "down":   # we are shorting into a rally back up
        hits = prices <= level + pad*TICK_SIZE
    else:                # long fade
        hits = prices >= level - pad*TICK_SIZE
    idx = np.argmax(hits)
    return None if hits.sum() == 0 else idx

def simulate_trade(entry_px, sl_px, tp1_px, tp2_px,
                   px_series, time_index):
    """
    Walk forward through prices; return tuple (net_R, exit_reason, hold_min)
    """
    risk = abs(sl_px - entry_px)
    for i,(p,t) in enumerate(zip(px_series, time_index)):
        if sl_px <= entry_px:   # long
            if p <= sl_px:  return -1.0, "stop",  (t-time_index[0]).total_seconds()/60
            if p >= tp1_px: tp1_hit = True
        else:                  # short
            if p >= sl_px:  return -1.0, "stop",  (t-time_index[0]).total_seconds()/60
            if p <= tp1_px: tp1_hit = True

        # break‑even logic
        if tp1_hit or (t - time_index[0]).total_seconds() >= BE_AFTER_MIN*60:
            sl_px = entry_px

        # TP2
        if sl_px <= entry_px:   # long
            if p >= tp2_px:  return TP2_R, "target2", (t-time_index[0]).total_seconds()/60
        else:                  # short
            if p <= tp2_px:  return TP2_R, "target2", (t-time_index[0]).total_seconds()/60

    return +0.0, "timer", (time_index[-1]-time_index[0]).total_seconds()/60

def main(db):
    if not os.path.exists(db):
        raise SystemExit(f"DB not found: {db}")

    with sqlite3.connect(db) as conn:
        sess = load_sessions(conn)

    trades = []
    for i,row in sess[sess["SinglePrints"] == 1].iterrows():
        edge_hi = row["SessionHigh"]   # simplification; you may store exact SP range
        edge_lo = row["SessionLow"]

        # look‑ahead window
        look = sess[(sess["idx"] > row["idx"]) &
                    (sess["idx"] <= row["idx"] + N_LOOKAHEAD) &
                    (sess["Sessions"].isin(QUAL_SESSIONS))]

        # prices for those sessions
        for _, nxt in look.iterrows():
            side  = "short" if nxt["SessionHigh"] >= edge_hi else "long" if nxt["SessionLow"] <= edge_lo else None
            if side is None:
                continue
            # --- define trade parameters -------------------------------
            if side == "short":
                entry = edge_hi + ENTRY_PAD_TICKS*TICK_SIZE
                sl    = edge_hi + SL_PAD_TICKS*TICK_SIZE
                tp1   = entry - TP1_R*abs(sl-entry)
                tp2   = entry - TP2_R*abs(sl-entry)
            else:
                entry = edge_lo - ENTRY_PAD_TICKS*TICK_SIZE
                sl    = edge_lo - SL_PAD_TICKS*TICK_SIZE
                tp1   = entry + TP1_R*abs(sl-entry)
                tp2   = entry + TP2_R*abs(sl-entry)

            # --- fetch tick prices slice (assumes parquet) -------------
            day = nxt["SessionStart"].date()
            try:
                ticks = pd.read_parquet("ticks.parquet", filters=[("date","=",str(day))])
            except Exception:
                continue
            px = ticks["Last"].values
            ts = pd.to_datetime(ticks["Timestamp"], utc=True).tz_convert("UTC")

            # simulate
            r, reason, hold = simulate_trade(entry, sl, tp1, tp2, px, ts)
            trades.append({
                "signal_sess": row["SessionStart"],
                "entry_sess" : nxt["SessionStart"],
                "side"       : side,
                "R"          : r,
                "exit"       : reason,
                "hold_min"   : hold
            })
            break   # only first valid revisit per signal

    if not trades:
        print("No qualifying trades.")
        return

    df = pd.DataFrame(trades)
    print("\n── Single‑Print fade results ──")
    hit = (df["R"] > 0).mean()
    print(f"Trades : {len(df)}")
    print(f"Hit‑rate : {hit:4.1%}")
    print(f"Avg R   : {df['R'].mean():.2f}")
    print("\nBreakdown:\n", df.groupby("exit")["R"].agg(["count","mean"]))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_FILE)
    args = parser.parse_args()
    main(args.db)
