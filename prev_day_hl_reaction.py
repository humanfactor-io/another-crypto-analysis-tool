"""prev_day_hl_reaction.py

CLI tool that answers: *How often does price during each session react
(touch or break) the **previous day's High and/or Low**?*

It loads `daily_summary` and `session_summary` from `crypto_data.db`,
aligns everything to the configured exchange time‑zone, then outputs:

    Session   PctPrevHigh  PctPrevLow  PctBoth  SampleSize
    -------   -----------  ----------  -------  ----------
    Asia         62.3%       55.1%      40.4%        450
    London       78.7%       61.2%      50.0%        448
    NewYork      70.1%       59.6%      45.5%        447

By default it looks back **6 months** and ignores the current
still‑unfinished trading day.
"""

from __future__ import annotations

import argparse, os, sqlite3, datetime as dt
import pandas as pd
import numpy as np
import config

# ---------------------------------------------------------------
#  Helpers copied from monday_stats_cli (tz handling)
# ---------------------------------------------------------------

def _to_exchange_time(ts: pd.Series | pd.DatetimeIndex) -> pd.Series:
    ts = pd.to_datetime(ts, utc=True)
    if getattr(config, "EXCHANGE_TZ", None):
        return ts.dt.tz_convert(config.EXCHANGE_TZ).dt.tz_localize(None)
    offset = getattr(config, "EXCHANGE_UTC_OFFSET_HRS", 0)
    return (ts + pd.Timedelta(hours=offset)).dt.tz_localize(None)

# ---------------------------------------------------------------
#  Core logic
# ---------------------------------------------------------------

DEFAULT_DB = "crypto_data.db"
SESSION_TABLE = "session_summary"
DAILY_TABLE = "daily_summary"


def load_tables(db_path: str):
    """Return daily_df (Date index) and session_df (records)."""
    with sqlite3.connect(db_path) as conn:
        daily = pd.read_sql(f"SELECT * FROM {DAILY_TABLE}", conn, parse_dates=["Date"]).set_index("Date")
        session = pd.read_sql(
            f"SELECT * FROM {SESSION_TABLE}",
            conn,
            parse_dates=["SessionStart", "SessionEnd", "Date"],
        )
    # ensure expected cols exist
    req_daily = {"DailyHigh", "DailyLow"}
    if not req_daily.issubset(daily.columns):
        raise ValueError(f"{DAILY_TABLE} missing columns {req_daily - set(daily.columns)}")
    req_sess = {"SessionHigh", "SessionLow", "SessionStart", "Sessions"}
    if not req_sess.issubset(session.columns):
        raise ValueError(f"{SESSION_TABLE} missing columns {req_sess - set(session.columns)}")
    return daily, session


def calc_reaction_stats(daily_df: pd.DataFrame, session_df: pd.DataFrame, months_back: int = 6,
                         tolerance: float | None = None):
    """Return stats DF per session and raw annotated session_df."""
    sess = session_df.copy()
    sess["ex_ts"] = _to_exchange_time(sess["SessionStart"])

    # drop current (in‑progress) calendar day in exchange tz
    today_ex = _to_exchange_time(pd.Series([pd.Timestamp.utcnow()]))[0].date()
    sess = sess[sess["ex_ts"].dt.date < today_ex]

    since = sess["ex_ts"].max() - pd.DateOffset(months=months_back)
    sess = sess[sess["ex_ts"] >= since]

    # map previous day high/low
    prev_dates = (sess["ex_ts"].dt.date - pd.Timedelta(days=1)).astype("datetime64[ns]")
    prev_daily = daily_df.loc[daily_df.index.isin(prev_dates)]
    # build dicts for fast map
    high_map = prev_daily["DailyHigh"].to_dict()
    low_map = prev_daily["DailyLow"].to_dict()

    sess["prev_high"] = prev_dates.map(lambda d: high_map.get(d, np.nan))
    sess["prev_low"] = prev_dates.map(lambda d: low_map.get(d, np.nan))

    tol = tolerance if tolerance is not None else 0.0
    sess["touch_high"] = sess["SessionHigh"] >= sess["prev_high"] - tol
    sess["touch_low"] = sess["SessionLow"] <= sess["prev_low"] + tol

    grp = sess.groupby("Sessions")
    stats = pd.DataFrame({
        "SampleSize": grp.size(),
        "PctPrevHigh": 100 * grp["touch_high"].mean(),
        "PctPrevLow":  100 * grp["touch_low"].mean(),
        "PctBoth":     100 * grp.apply(lambda g: (g["touch_high"] & g["touch_low"]).mean()),
    }).reset_index().sort_values("Sessions")

    return stats, sess

# ---------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------

def cli_main():
    p = argparse.ArgumentParser(description="Back‑test reactions to previous day's High / Low by session")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite DB containing session_summary & daily_summary")
    p.add_argument("--months", type=int, default=6, help="Look‑back window in months (default: 6)")
    p.add_argument("--tol", type=float, default=0.0, help="Price tolerance in same units as data (default: 0)")
    args = p.parse_args()

    if not os.path.exists(args.db):
        p.error(f"Database not found: {args.db}")

    daily, session = load_tables(args.db)
    stats, _ = calc_reaction_stats(daily, session, args.months, args.tol)

    print(f"\nReaction to previous day's High / Low (last {args.months} months)\n")
    print(stats.to_string(index=False, formatters={
        "PctPrevHigh": lambda x: f"{x:5.1f}%",
        "PctPrevLow": lambda x: f"{x:5.1f}%",
        "PctBoth": lambda x: f"{x:5.1f}%",
    }))


if __name__ == "__main__":
    cli_main() 