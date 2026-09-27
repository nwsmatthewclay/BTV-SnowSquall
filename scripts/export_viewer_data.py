"""Export object history and viewer metadata from reconstructed object scans."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

def clean(v):
    if pd.isna(v): return None
    if hasattr(v, "item"):
        try: return v.item()
        except Exception: pass
    return v

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output-dir", default="data/derived/viewer")
    p.add_argument("--case-id", default="UNKNOWN")
    p.add_argument("--radar-site", default="UNKNOWN")
    args=p.parse_args()
    df=pd.read_csv(args.input)
    df["scan_time_utc"]=pd.to_datetime(df["scan_time_utc"],utc=True,errors="coerce")
    df=df.dropna(subset=["scan_time_utc"]).sort_values(["scan_time_utc","object_id"])
    if df.empty: raise SystemExit("No object records found.")
    features=[]
    for _,r in df.iterrows():
        geom=None
        try:
            if isinstance(r.get("geometry_wkt"),str) and r["geometry_wkt"]:
                geom=mapping(wkt.loads(r["geometry_wkt"]))
        except Exception: pass
        if geom is None: continue
        props={"track_id":int(r["object_id"]),"timestamp":r["scan_time_utc"].isoformat(),
               "radar_site":clean(r.get("radar_site",args.radar_site)),
               "max_reflectivity_dbz":clean(r.get("max_reflectivity_dbz")),
               "mean_reflectivity_dbz":clean(r.get("mean_reflectivity_dbz")),
               "area_km2":clean(r.get("area_km2")),"length_km":clean(r.get("length_km")),
               "width_km":clean(r.get("width_km")),"pixel_count":clean(r.get("pixel_count")),
               "core_pixel_count":clean(r.get("core_pixel_count")),
               "centroid_lat":clean(r.get("centroid_lat")),"centroid_lon":clean(r.get("centroid_lon")),
               "motion_speed_kt":clean(r.get("motion_speed_kt")),"motion_dir_deg":clean(r.get("motion_dir_deg")),
               "reflectivity_trend_dbz_per_hr":clean(r.get("reflectivity_trend_dbz_per_hr")),
               "probability_30min":None,"probability_trend":"not_scored"}
        features.append({"type":"Feature","geometry":geom,"properties":props})
    times=sorted({f["properties"]["timestamp"] for f in features})
    tracks=sorted({f["properties"]["track_id"] for f in features})
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    (out/"objects.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features},indent=2))
    (out/"manifest.json").write_text(json.dumps({
        "case_id":args.case_id,"radar_site":args.radar_site,"product":"Snow Squall Object Viewer",
        "data_quality":"historical_pilot","model_version":"object-reconstruction-pilot",
        "scan_times_utc":times,"track_ids":tracks,
        "probability_status":"placeholder_until_model_training",
        "source_csv":str(Path(args.input))
    },indent=2))
    print(f"Wrote viewer data: {len(features)} object features, {len(times)} scans, {len(tracks)} tracks")

if __name__=="__main__": main()
