"""Validate the contract of a live snow-squall object product.

This is an engineering/data-integrity gate. It intentionally does not judge
forecast skill. The current worker is probability-free, so probability fields
must remain null and product metadata must explicitly say not_scored.
"""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

def parse_dt(value):
    if not value: return None
    return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)

def validate(state_path:Path,geojson_path:Path,max_future_seconds:float=120.0)->dict:
    state=json.loads(state_path.read_text(encoding="utf-8"))
    geo=json.loads(geojson_path.read_text(encoding="utf-8"))
    assert geo.get("type")=="FeatureCollection","GeoJSON must be a FeatureCollection"
    metadata=geo.get("metadata",{})
    assert metadata.get("probability_status")=="not_scored","Probability status must remain not_scored"
    assert state.get("last_source"),"Worker state is missing last_source"
    assert state.get("last_scan_time_utc"),"Worker state is missing last_scan_time_utc"
    assert "last_object_count" in state,"Worker state is missing last_object_count"
    state_time=parse_dt(state["last_scan_time_utc"]); output_time=parse_dt(metadata.get("scan_time_utc"))
    assert state_time is not None and output_time is not None,"Output/state timestamps must be valid UTC datetimes"
    delta=abs((state_time-output_time).total_seconds())
    assert delta<=max_future_seconds,f"State/output scan times differ by {delta:.1f}s"
    now=datetime.now(timezone.utc)
    assert (state_time-now).total_seconds()<=max_future_seconds,"Product timestamp is in the future"
    features=geo.get("features",[])
    assert int(state["last_object_count"])==len(features),"State object count does not match GeoJSON"
    invalid_geometry=invalid_probability=invalid_timestamp=out_of_domain=0
    for feature in features:
        props=feature.get("properties",{}); geometry=feature.get("geometry")
        if not geometry or geometry.get("type")!="Polygon": invalid_geometry+=1
        for key in ("probability_15min","probability_30min","probability_45min","probability_60min"):
            value=props.get(key)
            if value is not None and not (0.0<=float(value)<=1.0): invalid_probability+=1
        ts=parse_dt(props.get("timestamp"))
        if ts is None: invalid_timestamp+=1
        elif abs((ts-output_time).total_seconds())>max_future_seconds: invalid_timestamp+=1
        lat=props.get("centroid_lat"); lon=props.get("centroid_lon")
        if lat is not None and lon is not None:
            lat=float(lat); lon=float(lon)
            if not (40.0<=lat<=47.0 and -79.0<=lon<=-68.0): out_of_domain+=1
    assert invalid_geometry==0,f"{invalid_geometry} live objects have non-Polygon geometry"
    assert invalid_probability==0,f"{invalid_probability} invalid probability values found"
    assert invalid_timestamp==0,f"{invalid_timestamp} invalid object timestamps found"
    assert out_of_domain==0,f"{out_of_domain} object centroids outside the BTV-domain guard"
    return {
        "status":"ready_for_unscored_live_object_delivery",
        "probability_status":metadata["probability_status"],
        "scan_time_utc":output_time.isoformat(),
        "source_file":metadata.get("source_file"),
        "object_count":len(features),
        "geometry_invalid":invalid_geometry,
        "probability_invalid":invalid_probability,
        "timestamp_invalid":invalid_timestamp,
        "centroids_outside_domain":out_of_domain,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--state",default="data/derived/live_tracker_state.json")
    parser.add_argument("--geojson",default="data/derived/live_objects.geojson")
    parser.add_argument("--max-future-seconds",type=float,default=120.0)
    args=parser.parse_args()
    print(json.dumps(validate(Path(args.state),Path(args.geojson),args.max_future_seconds),indent=2))

if __name__=="__main__": main()
