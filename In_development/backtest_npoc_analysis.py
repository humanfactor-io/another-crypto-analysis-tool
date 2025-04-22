#!/usr/bin/env python3
"""
poc_report.py   –   prints plain‑text PoC micro‑edge tables
"""

from __future__ import annotations
import argparse, sqlite3, textwrap
from pathlib import Path
import pandas as pd
from tabulate import tabulate


# ────────────────────────────────────────────────────────────────────────────
def show(df: pd.DataFrame,
         title: str,
         pct: bool = False,
         pct_columns: list[str] | None = None) -> None:
    """
    Print a DataFrame with Tabulate.
      pct = True                → multiply entire table by 100 and append '%'
      pct_columns = ['colA']    → convert only those columns to %
    """
    pct_columns = pct_columns or []

    if pct:
        df = (df * 100).round(1).astype(str) + " %"

    elif pct_columns:
        df = df.copy()
        for col in pct_columns:
            if col in df.columns:
                df[col] = (df[col] * 100).round(1).astype(str) + " %"

    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(tabulate(df, headers="keys", tablefmt="simple", floatfmt=",.1f"))


# ────────────────────────────────────────────────────────────────────────────
def load_views(conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.Series]:
    poc = pd.read_sql("SELECT * FROM poc_revisits_micro", conn)
    poc["origin_session"]  = poc["origin_session_id"].str.split('_').str[-1]
    poc["revisit_session"] = poc["revisit_session_id"].str.split('_').str[-1]

    q = poc["max_ofi_1s"].quantile([0.25, 0.5, 0.75])
    q25, q50, q75 = q[0.25], q[0.5], q[0.75]
    poc["ofi_bucket"] = pd.cut(
        poc["max_ofi_1s"],
        [-float("inf"), q25, q50, q75, float("inf")],
        labels=["Q1‑low", "Q2", "Q3", "Q4‑high"],
    )
    return poc, q


# ────────────────────────────────────────────────────────────────────────────
def main(db: Path) -> None:
    conn = sqlite3.connect(db)
    poc, q = load_views(conn)

    lat = (
        poc.groupby("poc_type")[["sessions_elapsed", "minutes_elapsed"]]
           .agg(MeanSess=("sessions_elapsed", "mean"),
                MedSess=("sessions_elapsed", "median"),
                MeanMin=("minutes_elapsed", "mean"),
                MedMin=("minutes_elapsed", "median"))
           .round(1)
    )
    show(lat, "Latency summary (all PoCs)")

    rej = (
        poc.groupby(["direction", "poc_type"])["reaction"]
           .apply(lambda s: (s == "Rejection").mean())
           .unstack("poc_type")
           .round(2)
    )
    show(rej, "Rejection probability by direction", pct=True)

    ofi_tbl = (
        poc.groupby(["ofi_bucket", "poc_type"])
           .agg(MedExc=("max_exc", "median"),
                RejRate=("reaction", lambda s: (s == "Rejection").mean()))
           .round({"MedExc": 0, "RejRate": 2})
    )
    show(ofi_tbl, "Reaction vs OFI quartile (Q1‑low … Q4‑high)",
         pct_columns=["RejRate"])

    flip = (
        poc.groupby(["delta_flip", "poc_type"])
           .agg(Count=("poc_id", "count"),
                MedExc=("max_exc", "median"),
                RejRate=("reaction", lambda s: (s == "Rejection").mean()))
           .round({"MedExc": 0, "RejRate": 2})
    )
    flip.index = flip.index.set_levels(
        flip.index.levels[0].map({0: "No flip", 1: "Flip"}), level=0
    )
    show(flip, "Effect of delta‑flip", pct_columns=["RejRate"])

    lines = textwrap.dedent(f"""
        OFI quartile break‑points (absolute 1‑second OFI):
          • Q1‑low  < {q[0.25]:,.0f}
          • Q2      < {q[0.50]:,.0f}
          • Q3      < {q[0.75]:,.0f}
          • Q4‑high ≥ {q[0.75]:,.0f}
    """).strip()
    print("\n" + lines)
    conn.close()


# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Print PoC micro‑edge report")
    p.add_argument("--db", type=Path, default="crypto_data.db")
    args = p.parse_args()
    main(args.db)
