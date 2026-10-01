"""Build a frozen historical analog reference bundle for live/replay use."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from src.snow_squall.analogs import AnalogLibrary

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("features_csv")
    ap.add_argument("--output",required=True)
    ap.add_argument("--max-cases",type=int,default=0)
    args=ap.parse_args()
    df=pd.read_csv(args.features_csv)
    if "case_id" not in df.columns or "scan_time_utc" not in df.columns:
        raise SystemExit("features table requires case_id and scan_time_utc")
    df["_scan_dt"]=pd.to_datetime(df["scan_time_utc"],utc=True,errors="coerce")
    df=df[df["_scan_dt"].notna()].copy()
    if args.max_cases:
        cases=sorted(df["case_id"].astype(str).unique())
        df=df[df["case_id"].astype(str).isin(set(cases[-args.max_cases:]))].copy()
    df=df.drop(columns=["_scan_dt"])
    lib=AnalogLibrary.fit(df)
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); lib.save(out)
    print(f"Analog bundle: {out}")
    print(f"Reference rows: {len(df)}")
    print(f'Reference cases: {df["case_id"].astype(str).nunique()}')
    print(f"Features: {len(lib.feature_columns)}")

if __name__=="__main__": main()