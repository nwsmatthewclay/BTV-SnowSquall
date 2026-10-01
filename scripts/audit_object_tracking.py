"""Audit object-track continuity and radar-motion agreement."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def audit(frame: pd.DataFrame) -> dict:
    d=frame.copy()
    if d.empty:
        return {"records":0,"tracks":0}
    d["scan_dt"]=pd.to_datetime(d["scan_time_utc"],utc=True,errors="coerce")
    if "object_id" not in d.columns:
        raise ValueError("object_id required")
    d=d.sort_values(["radar_site","object_id","scan_dt"],kind="stable")
    g=d.groupby(["radar_site","object_id"],dropna=False,sort=False)
    dt=g["scan_dt"].diff().dt.total_seconds()/60.0
    speed=pd.to_numeric(d.get("motion_speed_kt"),errors="coerce")
    radar_speed=pd.to_numeric(d.get("radar_motion_speed_kt"),errors="coerce")
    radar_dir=pd.to_numeric(
        d["radar_motion_direction_deg"] if "radar_motion_direction_deg" in d.columns else pd.Series(np.nan,index=d.index),
        errors="coerce",
    )
    obj_dir_source = (
        d["motion_direction_deg"] if "motion_direction_deg" in d.columns
        else d["motion_dir_deg"] if "motion_dir_deg" in d.columns
        else pd.Series(np.nan,index=d.index)
    )
    obj_dir=pd.to_numeric(obj_dir_source,errors="coerce")
    direction_error=np.abs((obj_dir-radar_dir+180.0)%360.0-180.0)
    track_sizes=g.size()
    track_first=g["scan_dt"].min()
    track_last=g["scan_dt"].max()
    track_duration=(track_last-track_first).dt.total_seconds()/60.0
    out={
        "records":int(len(d)),
        "tracks":int(g.ngroups),
        "multi_scan_tracks":int((track_sizes>=2).sum()),
        "singleton_tracks":int((track_sizes==1).sum()),
        "singleton_track_fraction":float((track_sizes==1).mean()) if len(track_sizes) else 0.0,
        "median_track_scans":float(track_sizes.median()),
        "p90_track_scans":float(track_sizes.quantile(.90)),
        "median_track_duration_min":float(track_duration.median()) if len(track_duration) else 0.0,
        "p90_track_duration_min":float(track_duration.quantile(.90)) if len(track_duration) else 0.0,
        "gaps_gt_10min":int((dt>10).sum()),
        "impossible_speed_over_90kt":int((speed>90).sum()),
        "radar_motion_available":int(radar_speed.notna().sum()),
        "radar_motion_high_confidence":int(pd.to_numeric(d.get("radar_motion_confidence"),errors="coerce").fillna(0).ge(.5).sum()),
        "median_object_radar_motion_direction_error_deg":float(direction_error.dropna().median()) if direction_error.notna().any() else None,
        "edge_touch_fraction":float(pd.Series(d.get("touches_grid_edge",False)).fillna(False).astype(bool).mean()),
    }
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    report=audit(pd.read_csv(args.input_csv))
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
