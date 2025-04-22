import streamlit as st, pandas as pd, sqlite3, os, datetime
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Rectangle

DB_FILE   = "crypto_data.db"
TICK_FILE = "BTCUSDT_PERP_BINANCE_normalized.txt"

ROT_TBL   = "rotation_trades"
KEY_TBL   = "btc_key_levels"

TICK_COLS = ["Timestamp","Open","High","Low","Close","Volume",
             "Trades","BidVolume","AskVolume"]

TIMEFRAME = {"5 m":"5min","15 m":"15min","30 m":"30min",
             "1 H":"1H","4 H":"4H","12 H":"12H"}

# ── loaders ─────────────────────────────────────────────────────────
@st.cache_data
def load_trades():
    if not os.path.exists(DB_FILE): return None
    df = pd.read_sql(f"SELECT * FROM {ROT_TBL}", sqlite3.connect(DB_FILE),
                     parse_dates=["entry_ts","exit_ts"])
    df.set_index("entry_ts", inplace=True)
    return df

@st.cache_data
def load_monday_levels():
    if not os.path.exists(DB_FILE): return None
    df = pd.read_sql(
        "SELECT SessionStartUTC, MondayHigh, MondayLow "
        "FROM btc_key_levels WHERE MondayHigh IS NOT NULL",
        sqlite3.connect(DB_FILE),
        parse_dates=["SessionStartUTC"])
    df["SessionStartUTC"] = df["SessionStartUTC"].dt.tz_localize(None)
    df.set_index("SessionStartUTC", inplace=True)
    return df

@st.cache_data
def load_ticks(start_d, end_d):
    if not os.path.exists(TICK_FILE): return None
    df = pd.read_csv(TICK_FILE, names=TICK_COLS, header=None)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df[(df["Timestamp"].dt.date >= start_d) &
            (df["Timestamp"].dt.date <= end_d)]
    df.set_index("Timestamp", inplace=True)
    return df

def resample(t, tf):
    return (t.resample(tf)
              .agg({"Open":"first","High":"max","Low":"min",
                    "Close":"last","Volume":"sum"})
              .dropna(subset=["Open","High","Low","Close"]))

# ── UI ──────────────────────────────────────────────────────────────
st.set_page_config(layout="wide")
st.title("Monday‑Rotation – target hits & trailing stop")

tr_all = load_trades()
key_df = load_monday_levels()
if tr_all is None: st.error("rotation_trades missing."); st.stop()

min_d,max_d = tr_all.index.date.min(), tr_all.index.date.max()
c1,c2,c3 = st.columns(3)
with c1: start_d = st.date_input("Start", max_d- datetime.timedelta(days=5),
                                 min_value=min_d,max_value=max_d)
with c2: end_d   = st.date_input("End",   max_d,
                                 min_value=min_d,max_value=max_d)
with c3: tf_lbl  = st.selectbox("TF", list(TIMEFRAME.keys()),1)
tf = TIMEFRAME[tf_lbl]

show_targets = st.checkbox("🎯 targets only", True)

# ── draw -----------------------------------------------------------------
if st.button("Render"):
    ticks = load_ticks(start_d, end_d)
    if ticks is None or ticks.empty: st.error("No ticks."); st.stop()
    ohlc = resample(ticks, tf)
    if ohlc.empty: st.error("No candles."); st.stop()

    # filter trades
    tr = tr_all.copy(); tr.index = tr.index.tz_localize(None)
    tr = tr[(tr.index >= ohlc.index[0]) & (tr.index <= ohlc.index[-1])]
    if show_targets: tr = tr[tr.reason=="target"]

    mc  = mpf.make_marketcolors(up='#26a69a', down='#ef5350', inherit=True)
    stl = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')
    fig,axl = mpf.plot(ohlc, type='candle', volume=True,
                       style=stl, figsize=(16,9), returnfig=True,
                       title=f"{start_d} → {end_d}  ({tf_lbl})")
    ax = axl[0]; idx = ohlc.index
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.0f'))

    # cyan Monday bands
    if key_df is not None:
        k = key_df[(key_df.index >= idx[0]) & (key_df.index <= idx[-1])]
        for m in k.itertuples():
            w_start = m.Index.normalize(); w_end = w_start+datetime.timedelta(days=5)
            x0 = idx.get_indexer([max(w_start,idx[0])],method='nearest')[0]
            x1 = idx.get_indexer([min(w_end,idx[-1])],method='nearest')[0]
            ax.add_patch(Rectangle((x0-0.4,m.MondayLow),
                        (x1-x0)+0.8, m.MondayHigh-m.MondayLow,
                        color='#00BCD4', alpha=0.08,zorder=0))

    # helper
    bar = lambda ts: int(idx.get_indexer([ts],method='nearest')[0])

    # plot trades
    for t in tr.itertuples():
        mid = (t.entry + (t.exit if t.reason=="target" else t.stop_ticks*0))/2
        x0,x1 = bar(t.Index), bar(t.exit_ts.tz_localize(None))
        col   = "lime" if t.net_R>0 else "red"
        ax.add_patch(Rectangle((x0-0.4,min(t.entry,t.exit)),
                     (x1-x0)+0.8, abs(t.exit-t.entry),
                     color='yellow', alpha=.15,zorder=1))
        # stops/targets
        stop0 = t.entry - t.direction* t.stop_ticks*0.10
        stop_trail = mid
        ax.hlines(stop0,x0,x1,colors='red',linestyles='dashed')
        if t.reason=="target":
            ax.hlines(stop_trail,x0,x1,colors='purple',linestyles='dashed')
            ax.hlines(t.exit,x0,x1,colors='blue',linestyles='dashed')
        # markers
        mark = "^" if t.direction==1 else "v"
        ax.scatter(x0,t.entry,marker=mark,color=col,s=90,zorder=5)
        ax.scatter(x1,t.exit,marker="x",color='orange',s=70,zorder=5)
        ax.text(x1+0.3,t.exit,f"{t.net_R:.2f} R",color=col,fontsize=8)

    st.caption("cyan = Monday range • red dashed = initial stop • purple dashed = trail stop • blue dashed = target")
    st.pyplot(fig); plt.close(fig)
