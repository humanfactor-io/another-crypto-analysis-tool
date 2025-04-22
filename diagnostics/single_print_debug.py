#!/usr/bin/env python3
"""
single_print_debug.py  –  fade‑into‑single‑print back‑test with verbose
skips so you can see why a signal is rejected.

Example
-------
python single_print_debug.py --db crypto_data.db         \
       --look 6 --entry 0.5 --stop 8                    \
       --sessions Asia London NewYork Overnight         \
       --price-step 10
"""
import argparse, os, sqlite3, datetime as dt
import pandas as pd, numpy as np


# ─── helpers ───────────────────────────────────────────────────────────
def load_sessions(conn):
    q = """
    SELECT *, strftime('%Y-%m-%d %H:%M:%S',SessionStart) AS ts
    FROM session_summary
    ORDER BY SessionStart
    """
    df = pd.read_sql(q, conn, parse_dates=["SessionStart", "SessionEnd"])
    df["idx"] = np.arange(len(df))
    return df


def simulate_trade(entry, sl, tp1, tp2, px, ts, be_after):
    """Return (R‑multiple, exit_reason, hold_minutes)."""
    risk = abs(sl - entry)
    tp1_hit = False
    for p, t in zip(px, ts):
        if sl > entry:  # short
            if p >= sl:
                return -1.0, "stop", (t - ts[0]).total_seconds() / 60
            if p <= tp1:
                tp1_hit = True
        else:           # long
            if p <= sl:
                return -1.0, "stop", (t - ts[0]).total_seconds() / 60
            if p >= tp1:
                tp1_hit = True

        # break even
        if tp1_hit or (t - ts[0]).total_seconds() >= be_after * 60:
            sl = entry

        # TP2
        if sl > entry:      # short
            if p <= tp2:
                return 2.0, "target2", (t - ts[0]).total_seconds() / 60
        else:               # long
            if p >= tp2:
                return 2.0, "target2", (t - ts[0]).total_seconds() / 60

    return 0.0, "timer", (ts[-1] - ts[0]).total_seconds() / 60


# ─── main routine ──────────────────────────────────────────────────────
def main(args):
    if not os.path.exists(args.db):
        raise SystemExit(f"DB not found: {args.db}")

    with sqlite3.connect(args.db) as conn:
        sess = load_sessions(conn)

    print(f"[INFO] Sessions loaded          : {len(sess):,}")
    print(f"[INFO] Single‑print signals      : {(sess['SinglePrints']==1).sum():,}")
    print(f"[INFO] Allowed entry sessions    : {', '.join(sorted(args.sessions))}\n")

    trades = []
    for _, sig in sess[sess["SinglePrints"] == 1].iterrows():
        edge_hi, edge_lo = sig["SessionHigh"], sig["SessionLow"]

        look = sess[(sess["idx"] > sig["idx"]) &
                    (sess["idx"] <= sig["idx"] + args.look)]
        if look.empty:
            print("skip:", sig["SessionStart"], "→ no look‑ahead sessions")
            continue

        touched = False
        for _, nxt in look.iterrows():
            if nxt["Sessions"] not in args.sessions:
                print("skip:", nxt["SessionStart"], "→ session filter")
                continue

            side = None
            if nxt["SessionHigh"] >= edge_hi + args.entry:
                side = "short"
            elif nxt["SessionLow"] <= edge_lo - args.entry:
                side = "long"
            else:
                print("skip:", nxt["SessionStart"], "→ edge not touched")
                continue

            # price levels
            if side == "short":
                entry = edge_hi + args.entry
                sl    = edge_hi + args.stop
                tp1   = entry - (sl - entry)
                tp2   = entry - 2 * (sl - entry)
            else:
                entry = edge_lo - args.entry
                sl    = edge_lo - args.stop
                tp1   = entry + (entry - sl)
                tp2   = entry + 2 * (entry - sl)

            # ----- load ticks (robust col detection) ------------------
            day = nxt["SessionStart"].floor("D")
            try:
                ticks = pd.read_parquet("ticks.parquet")
            except Exception as e:
                print("skip:", nxt["SessionStart"], "→ parquet load fail:", e)
                continue

            # detect timestamp column
            if "Timestamp" in ticks.columns:
                ts_col = "Timestamp"
            elif "ts" in ticks.columns:
                ticks.rename(columns={"ts": "Timestamp"}, inplace=True)
                ts_col = "Timestamp"
            else:
                print("skip:", nxt["SessionStart"], "→ no Timestamp col in parquet")
                continue

            ticks[ts_col] = pd.to_datetime(ticks[ts_col], utc=True)
            day_mask = (ticks[ts_col] >= day) & (ticks[ts_col] < day + dt.timedelta(days=1))
            day_px = ticks.loc[day_mask]
            if day_px.empty:
                print("skip:", nxt["SessionStart"], "→ tick slice empty")
                continue

            price_col = "Last" if "Last" in day_px.columns else day_px.columns[-1]
            px = day_px[price_col].to_numpy(float)
            ts = day_px[ts_col].to_numpy()

            r, reason, hold = simulate_trade(entry, sl, tp1, tp2, px, ts, args.be)
            trades.append(dict(signal=sig["SessionStart"], entry=nxt["SessionStart"],
                               side=side, R=r, exit=reason, hold_m=hold))
            touched = True
            break  # first valid touch only

        if not touched:
            print("skip:", sig["SessionStart"], "→ no qualifying touch")

    # ── summary ───────────────────────────────────────────────────────
    print("\n── Single‑Print reaction summary ──")
    if not trades:
        print("No qualifying trades after all filters.")
        return

    df = pd.DataFrame(trades)
    print(f"Trades   : {len(df)}")
    print(f"Hit‑rate : {(df['R'] > 0).mean():.1%}")
    print(f"Avg R    : {df['R'].mean():.2f}\n")
    print(df.groupby("exit")["R"].agg(count="count", avg_R="mean"))


# ─── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser("Single‑print fade debug back‑test")
    ap.add_argument("--db", default="crypto_data.db")
    ap.add_argument("--entry", type=float, default=1.0, help="entry pad USD")
    ap.add_argument("--stop",  type=float, default=6.0, help="stop pad USD")
    ap.add_argument("--look",  type=int,   default=3,   help="look‑ahead sessions")
    ap.add_argument("--be",    type=int,   default=60,  help="minutes before BE")
    ap.add_argument("--price-step", type=float, default=10.0)  # informational
    ap.add_argument("--sessions", nargs="+",
                    default=["Asia", "London", "NewYork"],
                    help="allowed entry sessions")
    main(ap.parse_args())
