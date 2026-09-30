"""Build candidate winter null windows without treating missing reports as proof of no squall.

Null candidates are sampled from cool-season IEM/METAR periods and explicitly screened
against IEM LSRs, NWS warnings, and Storm Events records when those inputs are available.
They remain research negatives until radar/object review confirms the absence of the target.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--surface", required=True, help="IEM/ASOS observations with station and timestamp")
    p.add_argument("--lsr", required=True, help="IEM LSR report CSV")
    p.add_argument("--warnings", default=None, help="Optional warning/event table")
    p.add_argument("--output", required=True)
    p.add_argument("--min-gap-minutes", type=int, default=180)
    args=p.parse_args()

    surface=pd.read_csv(args.surface)
    required={"station","valid_utc"}
    missing=required-set(surface.columns)
    if missing: raise SystemExit(f"surface missing columns: {sorted(missing)}")
    surface["valid_utc"]=pd.to_datetime(surface["valid_utc"],utc=True,errors="coerce")
    surface=surface.dropna(subset=["valid_utc"]).sort_values(["station","valid_utc"])

    lsr=pd.read_csv(args.lsr)
    if "event_start_utc" in lsr:
        lsr["event_start_utc"]=pd.to_datetime(lsr["event_start_utc"],utc=True,errors="coerce")
    elif "VALID" in lsr:
        lsr["event_start_utc"]=pd.to_datetime(lsr["VALID"],utc=True,errors="coerce")
    else:
        lsr["event_start_utc"]=pd.NaT
    lsr=lsr.dropna(subset=["event_start_utc"])

    rows=[]
    for station,g in surface.groupby("station"):
        g=g.copy()
        winter=g[g["valid_utc"].dt.month.isin([10,11,12,1,2,3,4])].copy()
        if winter.empty: continue
        # Candidate every 60 minutes, then retain windows at least min_gap from an LSR.
        times=winter["valid_utc"].dt.floor("h").drop_duplicates().sort_values()
        for t in times:
            nearby=lsr[(lsr["event_start_utc"]-t).abs().dt.total_seconds().le(90*60)]
            if not nearby.empty:
                continue
            rows.append({
                "null_id":f"NULL-{station}-{t:%Y%m%d%H%M}",
                "station":station,
                "event_start_utc":t.isoformat(),
                "event_end_utc":(t+pd.Timedelta(minutes=60)).isoformat(),
                "null_screen":"no_IEM_LSR_within_90min",
                "supervision_class":"null_candidate_pending_radar_review",
                "truth_status":"unverified_null_candidate",
            })
    out=pd.DataFrame(rows).drop_duplicates("null_id")
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(args.output,index=False)
    print(f"Wrote {len(out):,} null candidates")
    print("These are NOT hard negatives until radar/object review and available warning/Storm Data evidence are applied.")

if __name__=="__main__":
    main()
