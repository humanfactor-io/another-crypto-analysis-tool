#!/usr/bin/env python3
"""
poc_revisit_analyzer.py – v1.4  (Z‑scores + delta‑spikes)
---------------------------------------------------------
Adds:
  • Q9  Distance‑weighted Z‑score buckets
  • Q10 Delta‑spike conditioning (origin & revisit)
Keeps all prior latency, directional, reaction analytics.
"""

from __future__ import annotations
import argparse, sqlite3, sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Dict

import pandas as pd
import numpy as np

# ── pretty console (optional) ───────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table  import Table
    RICH=True
except ImportError:
    RICH=False
    class Console:                                    # noqa
        def print(self,*a,**k): print(*a)
        def rule(self,*a,**k): print("-"*60)
    class Table:                                     # noqa
        def __init__(self,*a,**k):pass
        def add_column(self,*a,**k):pass
        def add_row(self,*a,**k):pass
console=Console()

# ── config ──────────────────────────────────────────────────────────────────
try:
    import config
    DB_PATH=Path(getattr(config,"DB_FILE","crypto_data.db"))
except ImportError:
    DB_PATH=Path("crypto_data.db")

TOLERANCE_TICKS     =0.5
QUALIFYING_SESSIONS ={"Asia","London","NewYork"}

PoCType  = Literal["VOLUME","TIME"]
DirClass = Literal["Upper","Lower"]

# ── dataclasses ─────────────────────────────────────────────────────────────
@dataclass(slots=True,frozen=True)
class Session:
    session_id:str
    start: datetime; end: datetime
    name:  str
    close: float
    delta: float                # SessionDelta
    vpoc:  float|None
    tpoc:  float|None
    low:   float; high: float
    def poc_items(self):
        out=[]
        if self.vpoc is not None and pd.notna(self.vpoc):
            out.append(("VOLUME",self.vpoc,"Upper"if self.vpoc>self.close else"Lower"))
        if self.tpoc is not None and pd.notna(self.tpoc):
            out.append(("TIME",self.tpoc,"Upper"if self.tpoc>self.close else"Lower"))
        return out

@dataclass(slots=True)
class RevisitEvent:
    poc_id: str
    origin_session_id:str; origin_session_start:datetime
    poc_type:PoCType; direction:DirClass
    poc_price:float
    dist_orig:float             # |PoC‑close|
    origin_delta:float          # order‑flow delta
    revisited:bool=False
    revisit_session_id:str|None=None
    revisit_session_start:datetime|None=None
    revisit_delta:float|None=None
    sessions_elapsed:int|None=None
    minutes_elapsed:float|None=None
    hi_off:float|None=None; lo_off:float|None=None
    max_exc:float|None=None; close_off:float|None=None
    reaction:str|None=None
    zscore:float|None=None      # distance‑weighted z
    origin_spike:bool|None=None # |delta|>2σ
    revisit_spike:bool|None=None

# ── helpers ─────────────────────────────────────────────────────────────────
def connect(db:Path)->sqlite3.Connection:
    conn=sqlite3.connect(db,check_same_thread=False); conn.row_factory=sqlite3.Row
    console.print(f"Connected → {db}"); return conn

def load_sessions(conn)->List[Session]:
    q=f"""
     SELECT strftime('%Y-%m-%d',Date)||'_'||Sessions AS session_id,
            SessionStart,SessionEnd,Sessions AS name,
            SessionClose AS close, SessionDelta AS delta,
            SessionVPOC AS vpoc, TPO_POC AS tpoc,
            SessionLow AS low, SessionHigh AS high
     FROM session_summary
     WHERE Sessions IN ({','.join(f"'{s}'" for s in QUALIFYING_SESSIONS)})
     ORDER BY SessionStart;"""
    df=pd.read_sql(q,conn,parse_dates=["SessionStart","SessionEnd"])
    out=[]
    for r in df.itertuples(index=False):
        out.append(Session(
            session_id=r.session_id,
            start=r.SessionStart.tz_localize(timezone.utc)
                    if r.SessionStart.tzinfo is None else r.SessionStart,
            end  =r.SessionEnd.tz_localize(timezone.utc)
                    if r.SessionEnd.tzinfo is None else r.SessionEnd,
            name =r.name,
            close=float(r.close), delta=float(r.delta),
            vpoc=float(r.vpoc) if pd.notna(r.vpoc) else None,
            tpoc=float(r.tpoc) if pd.notna(r.tpoc) else None,
            low=float(r.low), high=float(r.high)
        ))
    return out

def touches(lo:float,hi:float,price:float,tol:float)->bool:
    return (lo-tol)<=price<=(hi+tol)

# ── core analysis ───────────────────────────────────────────────────────────
def analyse(sess:List[Session],tol:float)->List[RevisitEvent]:
    naked:Dict[str,RevisitEvent]={}; evs=[]
    # pre‑compute delta σ for spike threshold
    deltas=np.array([s.delta for s in sess]); delta_sig=np.nanstd(deltas)
    for i,s in enumerate(sess):
        for ptype,pprice,dirc in s.poc_items():
            pid=f"{s.session_id}_{ptype}"
            ev=RevisitEvent(
                pid,s.session_id,s.start,ptype,dirc,pprice,
                dist_orig=abs(pprice-s.close), origin_delta=s.delta)
            ev.origin_spike=abs(s.delta)>2*delta_sig
            evs.append(ev); naked[pid]=ev
        for pid in list(naked):
            ev=naked[pid]
            if ev.origin_session_id==s.session_id: continue
            if touches(s.low,s.high,ev.poc_price,tol):
                ev.revisited=True; ev.revisit_session_id=s.session_id
                ev.revisit_session_start=s.start; ev.revisit_delta=s.delta
                ev.revisit_spike=abs(s.delta)>2*delta_sig
                oi=next(k for k,x in enumerate(sess) if x.session_id==ev.origin_session_id)
                ev.sessions_elapsed=i-oi
                ev.minutes_elapsed=max(0,(s.start-sess[oi].end).total_seconds()/60)
                ev.hi_off=s.high-ev.poc_price; ev.lo_off=ev.poc_price-s.low
                ev.max_exc=max(ev.hi_off,ev.lo_off)
                ev.close_off=s.close-ev.poc_price
                ev.reaction=("Rejection" if 
                    (ev.direction=="Upper" and ev.close_off<0) or
                    (ev.direction=="Lower" and ev.close_off>0) else "Acceptance")
                del naked[pid]
    console.print(f"Events: {len(evs):,}  (revisited {sum(e.revisited for e in evs):,})")
    # global z‑score on dist_orig per PoC type
    for ptype in ("TIME","VOLUME"):
        dists=[e.dist_orig for e in evs if e.poc_type==ptype]
        mu=np.mean(dists); sig=np.std(dists) or 1
        for e in evs:
            if e.poc_type==ptype: e.zscore=(e.dist_orig-mu)/sig
    return evs

# ── stats lab ───────────────────────────────────────────────────────────────
def sname(full:str)->str: return full.split('_')[-1]

def build_stats(df:pd.DataFrame)->dict[str,pd.DataFrame]:
    out={}
    df["origin_session"]=df.origin_session_id.str.split('_').str[-1]
    df["revisit_session"]=df.revisit_session_id.str.split('_').str[-1]
    rev=df[df.revisited]

    # prior tables (brief: origin_dist etc.)
    out["origin_dist"]=df.pivot_table(index="origin_session",columns="poc_type",
                                      values="poc_id",aggfunc="count",fill_value=0)
    out["revisit_dist"]=rev.pivot_table(index="revisit_session",columns="poc_type",
                                        values="poc_id",aggfunc="count",fill_value=0)
    lat_cols=dict(MeanMin=("minutes_elapsed","mean"),
                  MedMin =("minutes_elapsed","median"),
                  MeanSes=("sessions_elapsed","mean"),
                  MedSes =("sessions_elapsed","median"))
    out["latency_by_type"]=rev.groupby("poc_type").agg(**lat_cols).round(1)
    out["latency_by_origin"]=(rev.groupby(["origin_session","poc_type"])
                                .agg(**lat_cols).round(1).unstack("poc_type"))
    pct={}
    for n in (1,2,3,6):
        pct[f"≤{n}s"]=(rev.sessions_elapsed<=n).groupby(rev.poc_type).mean()
    out["latency_pct"]=pd.DataFrame(pct).round(2)
    out["prob_next_session"]=(
        df.groupby(["origin_session","poc_type"])
          .agg(Total=("poc_id","count"),Next=("sessions_elapsed",lambda x:(x==1).sum()))
          .assign(Prob=lambda d:d.Next/d.Total)
          .pivot_table(index="origin_session",columns="poc_type",values="Prob"))
    out["dir_origin_bias"]=df.groupby(["origin_session","direction","poc_type"]).size()\
                              .unstack("poc_type").fillna(0).astype(int)
    out["prob_next_dir"]=(
        df.groupby(["origin_session","direction","poc_type"])
          .agg(Total=("poc_id","count"),Next=("sessions_elapsed",lambda x:(x==1).sum()))
          .assign(Prob=lambda d:d.Next/d.Total)
          .pivot_table(index=["origin_session","direction"],columns="poc_type",values="Prob"))
    out["reaction_mag"]=(
        rev.groupby(["direction","poc_type"])
           .agg(MedMaxExc=("max_exc","median"), MedClOff=("close_off",lambda x:abs(x).median()))
           .round(1))
    ra=rev.groupby(["direction","poc_type","reaction"]).size().unstack("reaction").fillna(0)
    ra["Total"]=ra.sum(axis=1)
    ra["Rej%"]=(ra.Rejection/ra.Total).round(2); ra["Acc%"]=(ra.Acceptance/ra.Total).round(2)
    out["rej_acc"]=ra[["Rej%","Acc%"]]

    # ── NEW   Q9  Z‑score buckets ------------------------------------------
    rev["Zbucket"]=pd.cut(rev.zscore,[-np.inf,-1,1,np.inf],labels=["Low(<-1)","Mid(-1~1)","High(>1)"])
    out["z_reaction"]=(
        rev.groupby(["Zbucket","poc_type"])
           .agg(MedExc=("max_exc","median"), RejectRate=("reaction", lambda x:(x=="Rejection").mean()))
           .round({"MedExc":1,"RejectRate":2}))

    # ── NEW   Q10 Delta‑spike conditioning ---------------------------------
    def delta_tbl(col:str):
        g=rev.groupby([col,"poc_type"])
        return g.agg(Count=("poc_id","count"),
                     MedExc=("max_exc","median"),
                     Reject=("reaction",lambda x:(x=="Rejection").mean())).round({"MedExc":1,"Reject":2})
    out["delta_origin"]=delta_tbl("origin_spike")
    out["delta_revisit"]=delta_tbl("revisit_spike")

    return out

# ── util for printing ───────────────────────────────────────────────────────
def show(df:pd.DataFrame,title:str,pct:bool=False):
    if not RICH:
        console.rule(title)
        print((df*100 if pct else df).round(1 if pct else 0).to_string())
        return
    table=Table(title=title,header_style="bold cyan")
    table.add_column("")
    for c in df.columns: table.add_column(str(c),justify="right")
    for idx,row in df.iterrows():
        idx_str=" | ".join(map(str,idx)) if isinstance(idx,tuple) else str(idx)
        table.add_row(idx_str,*[
            f"{v*100:4.1f}%" if pct else f"{v:,.1f}" if isinstance(v,float)
            else f"{v:,.0f}" for v in row])
    console.rule(title); console.print(table)

# ── persistence ────────────────────────────────────────────────────────────
def save(conn,df,table):
    if df.empty:return
    d=df.copy()
    for c in d.select_dtypes("datetimetz").columns:
        d[c]=d[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    d.to_sql(table,conn,if_exists="replace",index=False)
    console.print(f"Wrote {len(df):,} rows → {table}")

# ── main ────────────────────────────────────────────────────────────────────
def main():
    p=argparse.ArgumentParser(description="PoC revisit stats + Z & delta spikes",
                              formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--db",type=Path,default=DB_PATH)
    p.add_argument("--tol",type=float,default=TOLERANCE_TICKS)
    p.add_argument("--table",default="poc_revisits")
    p.add_argument("--no-save",action="store_true")
    a=p.parse_args()

    conn=connect(a.db)
    sess=load_sessions(conn)
    if not sess: sys.exit("No sessions")

    evs=analyse(sess,a.tol)
    df=pd.DataFrame([asdict(e) for e in evs])
    if not a.no_save: save(conn,df,a.table)

    st=build_stats(df)
    show(st["origin_dist"],       "Q1 Origin")
    show(st["revisit_dist"],      "Q2 Revisit")
    show(st["latency_by_type"],   "Q3 Latency")
    show(st["latency_by_origin"], "Q3b Latency by origin")
    show(st["latency_pct"],       "Extra % hit ≤N",pct=True)
    show(st["prob_next_session"], "Q4 Next‑sess prob",pct=True)
    show(st["dir_origin_bias"],   "Q5 Directional origin")
    show(st["prob_next_dir"],     "Q6 Next‑sess prob by dir",pct=True)
    show(st["reaction_mag"],      "Q7 Reaction magnitude")
    show(st["rej_acc"],           "Q8 Rej vs Acc",pct=True)
    show(st["z_reaction"],        "Q9 Z‑bucket reaction")
    show(st["delta_origin"],      "Q10 Origin delta spike")
    show(st["delta_revisit"],     "Q10b Revisit delta spike")
    conn.close(); console.rule("[green]Done[/green]")

if __name__=="__main__":
    main()
