# monday_analysis.py  (v2 – aggregate across sessions)

import pandas as pd
import config   # expects EXCHANGE_TZ or EXCHANGE_UTC_OFFSET_HRS

# ----------------------------------------------------------------------
#  Helpers
# ----------------------------------------------------------------------
def _to_exchange_time(ts: pd.Series) -> pd.Series:
    """Return tz‑naive timestamps expressed in the chosen exchange zone."""
    ts = pd.to_datetime(ts, utc=True)
    if getattr(config, "EXCHANGE_TZ", None):
        return ts.dt.tz_convert(config.EXCHANGE_TZ).dt.tz_localize(None)
    offset = getattr(config, "EXCHANGE_UTC_OFFSET_HRS", 0)
    return (ts + pd.Timedelta(hours=offset)).dt.tz_localize(None)

def _week_id(ts: pd.Series) -> pd.Series:
    """Monday‑00:00 anchor of each week in exchange time."""
    monday = ts - pd.to_timedelta(ts.dt.weekday, unit="D")
    return monday.dt.floor("D")

# ----------------------------------------------------------------------
#  Core calculations
# ----------------------------------------------------------------------
def build_monday_and_week_table(summary_df: pd.DataFrame,
                                months_back: int = 6,
                                drop_current_week: bool = True) -> pd.DataFrame:
    """
    Returns a DataFrame with Monday‑range and full‑week range per week_id.
    Monday highs/lows are *aggregated across all sessions* whose local
    calendar date is Monday.
    """
    df = summary_df.copy()
    df["ex_ts"] = _to_exchange_time(df["SessionStart"])
    since = df["ex_ts"].max() - pd.DateOffset(months=months_back)
    df = df[df["ex_ts"] >= since]

    df["week_id"] = _week_id(df["ex_ts"])

    # Optionally remove the still‑in‑progress week so partial data
    # doesn't bias stats (e.g. Monday appears as both High & Low).
    if drop_current_week and not df.empty:
        now_ex = _to_exchange_time(pd.Series([pd.Timestamp.utcnow()]))[0]
        current_wk = _week_id(pd.Series([now_ex]))[0]
        df = df[df["week_id"] < current_wk]

    # --- Monday extremes aggregated across sessions  ------------------
    mon_rows = df[df["ex_ts"].dt.weekday == 0]
    mon_hl = mon_rows.groupby("week_id").agg(
        MondayHigh=("SessionHigh", "max"),
        MondayLow =("SessionLow",  "min")
    )

    # --- True weekly extremes -----------------------------------------
    week_hl = df.groupby("week_id").agg(
        WeeklyHigh=("SessionHigh", "max"),
        WeeklyLow =("SessionLow",  "min")
    )

    tbl = mon_hl.join(week_hl, how="inner").dropna()
    tbl["Mon_is_WkHigh"] = tbl["MondayHigh"] >= tbl["WeeklyHigh"] - 1e-8
    tbl["Mon_is_WkLow"]  = tbl["MondayLow"]  <= tbl["WeeklyLow"]  + 1e-8
    return tbl.reset_index()

def get_monday_stats(summary_df: pd.DataFrame,
                     key_levels_df: pd.DataFrame,
                     months_back: int = 6):
    """
    Returns:
        weekly_tbl – per‑week DataFrame (see build_monday_and_week_table)
        pct_dict   – dictionary of percentage statistics
    """
    wk = build_monday_and_week_table(summary_df, months_back, drop_current_week=True)

    pct = {
        "pct_monday_is_weekly_high_low": 100*(wk["Mon_is_WkHigh"] & wk["Mon_is_WkLow"]).mean(),
        "pct_monday_is_weekly_high":     100* wk["Mon_is_WkHigh"].mean(),
        "pct_monday_is_weekly_low":      100* wk["Mon_is_WkLow"].mean(),
    }

    # -------- Which session later breaks the Monday levels ------------
    sess = summary_df.copy()
    sess["ex_ts"]   = _to_exchange_time(sess["SessionStart"])
    sess["week_id"] = _week_id(sess["ex_ts"])

    # Keep only completed week_ids present in wk
    valid_wks = set(wk["week_id"])
    sess = sess[sess["week_id"].isin(valid_wks)]

    # Create mapping dicts to Monday highs/lows to avoid merge issues
    mon_high_map = wk.set_index('week_id')['MondayHigh']
    mon_low_map  = wk.set_index('week_id')['MondayLow']

    def _session_break_pct(sess_name: str):
        sub = sess[sess["Sessions"] == sess_name]
        hit_hi = sub["SessionHigh"] >= sub["week_id"].map(mon_high_map)
        hit_lo = sub["SessionLow"]  <= sub["week_id"].map(mon_low_map)
        base_map = {"London": "london", "NewYork": "ny", "Asia": "asia"}
        base = base_map.get(sess_name, sess_name.lower())
        return {
            f"pct_high_broken_{base}":      100 * hit_hi.mean(),
            f"pct_low_broken_{base}":       100 * hit_lo.mean(),
            f"pct_high_low_broken_{base}":  100 * (hit_hi & hit_lo).mean(),
        }

    for s in ("London", "NewYork", "Asia"):
        pct.update(_session_break_pct(s))

    # ------------------------------------------------------------------
    #  Collect week lists for each metric
    # ------------------------------------------------------------------
    week_lists = {}

    # Monday-based conditions
    wk['week_str'] = wk['week_id'].dt.strftime('%Y-%m-%d')
    week_lists['MonHL'] = wk.loc[wk['Mon_is_WkHigh'] & wk['Mon_is_WkLow'], 'week_str'].tolist()
    week_lists['MonHigh'] = wk.loc[wk['Mon_is_WkHigh'], 'week_str'].tolist()
    week_lists['MonLow'] = wk.loc[wk['Mon_is_WkLow'], 'week_str'].tolist()

    # Session break week lists
    sess['ex_ts']   = _to_exchange_time(sess['SessionStart'])
    sess['week_id'] = _week_id(sess['ex_ts'])

    def _calc_break_weeks(session_name:str, key_prefix:str):
        sub = sess[sess['Sessions']==session_name]
        weeks = mon_high_map.index
        hi_weeks = []
        lo_weeks = []
        for wk_id in weeks:
            wk_sub = sub[sub['week_id'] == wk_id]
            if wk_sub.empty:
                continue
            if wk_sub['SessionHigh'].max() >= mon_high_map[wk_id]:
                hi_weeks.append(wk_id)
            if wk_sub['SessionLow'].min() <= mon_low_map[wk_id]:
                lo_weeks.append(wk_id)
        both_weeks = sorted(set(hi_weeks) & set(lo_weeks))
        fmt = lambda arr: [p.strftime('%Y-%m-%d') for p in arr]
        week_lists[f'{key_prefix}_High'] = fmt(hi_weeks)
        week_lists[f'{key_prefix}_Low']  = fmt(lo_weeks)
        week_lists[f'{key_prefix}_HL']   = fmt(both_weeks)

    _calc_break_weeks('London','LDN')
    _calc_break_weeks('NewYork','NY')
    _calc_break_weeks('Asia','ASIA')

    return wk, pct, week_lists

def get_weeks_where_monday_is_weekly_hl(wk_tbl: pd.DataFrame):
    both = wk_tbl[wk_tbl["Mon_is_WkHigh"] & wk_tbl["Mon_is_WkLow"]]
    return both["week_id"].dt.strftime("%Y‑%m‑%d/%Y‑%m‑%d").tolist()

# ----------------------------------------------------------------------
#  Stand‑alone CLI wrapper
# ----------------------------------------------------------------------

import argparse, sqlite3, os

DEFAULT_DB = "crypto_data.db"
SESSION_TABLE = "session_summary"
TICK_TABLE = "tick_data"


def _load_table(conn, table, parse_dates=None):
    return pd.read_sql(f"SELECT * FROM {table}", conn, parse_dates=parse_dates)


def cli_main():
    parser = argparse.ArgumentParser(description="Print Monday / weekly statistics aligned to exchange week")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path (default: %(default)s)")
    parser.add_argument("--months", type=int, default=6, help="Look‑back window in months")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        parser.error(f"Database file not found: {args.db}")

    with sqlite3.connect(args.db) as conn:
        print(f"Loading '{SESSION_TABLE}' from {args.db} …")
        summary_df = _load_table(conn, SESSION_TABLE, parse_dates=["SessionStart", "SessionEnd"])

    wk_tbl, pct, wk_lists = get_monday_stats(summary_df, None, months_back=args.months)

    # Overlap LDN/NY break weeks
    mon_high_map = wk_tbl.set_index('week_id')['MondayHigh'].to_dict()
    with sqlite3.connect(args.db) as conn2:
        overlap_weeks = _weeks_overlap_break(conn2, wk_tbl, mon_high_map)

    print(f"\n=== Monday statistics (last {args.months} months) ===")
    ordered = [
        ("pct_monday_is_weekly_high_low", "Monday is BOTH weekly High & Low"),
        ("pct_monday_is_weekly_high", "Monday is Weekly High"),
        ("pct_monday_is_weekly_low", "Monday is Weekly Low"),
        ("pct_high_low_broken_london", "London breaks BOTH Mon High & Low"),
        ("pct_high_broken_london", "London breaks Monday High"),
        ("pct_low_broken_london", "London breaks Monday Low"),
        ("pct_high_low_broken_ny", "New York breaks BOTH Mon High & Low"),
        ("pct_high_broken_ny", "New York breaks Monday High"),
        ("pct_low_broken_ny", "New York breaks Monday Low"),
        ("pct_high_low_broken_asia", "Asia breaks BOTH Mon High & Low"),
        ("pct_high_broken_asia", "Asia breaks Monday High"),
        ("pct_low_broken_asia", "Asia breaks Monday Low"),
    ]
    for key, label in ordered:
        if key in pct:
            print(f"{label:40s}: {pct[key]:5.1f}%")

    special = get_weeks_where_monday_is_weekly_hl(wk_tbl)
    if special:
        print("\nWeeks where Monday was BOTH weekly High & Low:")
        for w in special:
            print("  ", w)

    if overlap_weeks:
        print("\nWeeks where Monday High was broken during LDN/NY overlap (13:30‑16:00 UTC):")
        for w in overlap_weeks:
            print("  ", w)

    print("\n--- Triggered weeks per criterion ---")
    name_map = {
        'MonHL':  'Monday is BOTH weekly High & Low',
        'MonHigh': 'Monday is Weekly High',
        'MonLow':  'Monday is Weekly Low',
        'LDN_HL': 'London breaks BOTH Mon High & Low',
        'LDN_High': 'London breaks Monday High',
        'LDN_Low':  'London breaks Monday Low',
        'NY_HL':  'New York breaks BOTH Mon High & Low',
        'NY_High':'New York breaks Monday High',
        'NY_Low': 'New York breaks Monday Low',
        'ASIA_HL':'Asia breaks BOTH Mon High & Low',
        'ASIA_High':'Asia breaks Monday High',
        'ASIA_Low':'Asia breaks Monday Low'
    }

    for key, weeks in wk_lists.items():
        label = name_map.get(key, key)
        if weeks:
            print(f"\n{label}:")
            for w in weeks:
                print("  ", w)

def _weeks_overlap_break(conn, wk_df, monday_high_map):
    """Return list of weeks where MondayHigh broken during LDN/NY overlap (13:30-16:00 UTC, Tue-Fri)."""
    weeks_triggered = []
    for wk_id, mon_high in monday_high_map.items():
        week_start = pd.Period(wk_id, freq='W-MON').start_time
        tue_date = (week_start + pd.Timedelta(days=1)).strftime('%Y-%m-%d')  # Tuesday
        sat_date = (week_start + pd.Timedelta(days=6)).strftime('%Y-%m-%d')  # Saturday 00:00 exclusive
        query = f"""
            SELECT MAX(High) as max_high
            FROM {TICK_TABLE}
            WHERE Timestamp >= '{tue_date} 00:00:00' AND Timestamp < '{sat_date} 00:00:00'
              AND time(Timestamp) >= '13:30:00' AND time(Timestamp) < '16:00:00';
        """
        max_high = conn.execute(query).fetchone()[0]
        if max_high is not None and max_high >= mon_high:
            weeks_triggered.append(week_start.strftime('%Y-%m-%d'))
    return weeks_triggered

if __name__ == "__main__":
    cli_main()
