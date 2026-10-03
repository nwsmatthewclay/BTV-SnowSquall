"""Build a static, multi-case historical viewer package from reconstructed objects."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

ENVIRONMENT_FIELDS = [
    ("SBCAPE", "sbcape_jkg", "J/kg"),
    ("SBCIN", "sbcin_jkg", "J/kg"),
    ("MLCAPE", "mlcape_jkg", "J/kg"),
    ("MLCIN", "mlcin_jkg", "J/kg"),
    ("MUCAPE", "mucape_jkg", "J/kg"),
    ("DCAPE", "dcape_jkg", "J/kg"),
    ("PWAT", "pwat_mm", "mm"),
    ("LCL", "lcl_m", "m"),
    ("RH 0–2 km", "rh_0_2km_pct", "%"),
    ("0–1 km wind", "wind_0_1km_kt", "kt"),
    ("0–3 km wind", "wind_0_3km_kt", "kt"),
    ("0–1 km shear", "shear_0_1km_kt", "kt"),
    ("0–3 km shear", "shear_0_3km_kt", "kt"),
    ("0–6 km shear", "shear_0_6km_kt", "kt"),
    ("0–3 km lapse", "lapse_rate_0_3km_c_km", "°C/km"),
    ("0–7.5 km lapse", "lapse_rate_0_7_5km_c_km", "°C/km"),
    ("WB 0–3 km", "wet_bulb_0_3km_c", "°C"),
    ("0–1 km SRH", "srh01_m2s2", "m²/s²"),
    ("SNSQ", "snsq", ""),
]

def clean(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value

def safe_name(*parts):
    raw = "_".join(str(p) for p in parts if str(p) not in ("", "nan", "None"))
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)

def object_properties(row, research_probabilities=None):
    props = {
        "track_key": f"{row.get('case_id', 'UNKNOWN')}:{row.get('radar_site', 'UNKNOWN')}:{row.get('object_id', 'UNKNOWN')}",
        "object_id": clean(row.get("object_id")),
        "case_id": clean(row.get("case_id")),
        "radar_site": clean(row.get("radar_site")),
        "timestamp": row["scan_time_utc"].isoformat(),
        "centroid_lat": clean(row.get("centroid_lat")),
        "centroid_lon": clean(row.get("centroid_lon")),
        "max_reflectivity_dbz": clean(row.get("max_reflectivity_dbz")),
        "mean_reflectivity_dbz": clean(row.get("mean_reflectivity_dbz")),
        "area_km2": clean(row.get("area_km2")),
        "length_km": clean(row.get("length_km")),
        "width_km": clean(row.get("width_km")),
        "aspect_ratio": clean(row.get("aspect_ratio")),
        "motion_speed_kt": clean(row.get("motion_speed_kt")),
        "motion_direction_deg": clean(row.get("motion_direction_deg")),
        "reflectivity_trend_dbz_per_hr": clean(row.get("reflectivity_trend_dbz_per_hr")),
        "age_scans": clean(row.get("age_scans")),
        "core_fraction": clean(row.get("core_fraction")),
        "environment_status": clean(row.get("environment_status")),
        "environment_source": clean(row.get("environment_source")),
        "environment_valid_time_utc": clean(row.get("environment_valid_time_utc")),
        "environment_age_minutes": clean(row.get("environment_age_minutes")),
        "track_event_associated": clean(row.get("track_event_associated")),
        "case_time_relation": clean(row.get("case_time_relation")),
    }
    if research_probabilities:
        props["research_probabilities"] = research_probabilities.get(
            (str(row.get("case_id")), str(row.get("radar_site")), str(row.get("object_id")), row["scan_time_utc"].isoformat()),
            {},
        )
    props["environment"] = {
        key: {"label": label, "value": clean(row.get(key)), "units": units}
        for label, key, units in ENVIRONMENT_FIELDS
    }
    return props

def read_frames(frames_root: Path, case_id: str, radar_site: str):
    path=frames_root/"data"/"cases"/f"{case_id}_{radar_site}"/"frames.json"
    if not path.exists():
        return [], None
    payload=json.loads(path.read_text(encoding="utf-8"))
    return payload.get("frames", []), payload.get("bounds")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--objects",required=True)
    parser.add_argument("--cases",required=True)
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--frames-root",default=None)
    parser.add_argument("--model-summary",default=None,help="Optional baseline_horizon_summary.json to embed as research-only viewer diagnostics.")
    parser.add_argument("--model-root",default=None,help="Optional root containing baseline_model_*m/oof_predictions.csv files for historical research-probability overlays.")
    parser.add_argument("--replay-dir",default=None,help="Optional historical replay directory containing GeoJSON outputs scored through the live model processor.")
    args=parser.parse_args()

    objects=pd.read_csv(args.objects)
    cases=pd.read_csv(args.cases)
    objects["scan_time_utc"]=pd.to_datetime(objects["scan_time_utc"],utc=True,errors="coerce")
    objects=objects.dropna(subset=["scan_time_utc","case_id","radar_site"]).copy()

    root=Path(args.output_dir)
    data_dir=root/"data"
    cases_dir=data_dir/"cases"
    cases_dir.mkdir(parents=True,exist_ok=True)
    frames_root=Path(args.frames_root) if args.frames_root else root
    model_summary=None
    research_probabilities={}
    if args.model_root:
        model_root=Path(args.model_root)
        for horizon in (15,30,45,60):
            pred_path=model_root/f"baseline_model_{horizon}m"/"oof_predictions.csv"
            if not pred_path.exists():
                continue
            try:
                pred=pd.read_csv(pred_path)
            except Exception:
                continue
            required={"case_id","radar_site","object_id","scan_time_utc","oof_probability"}
            if not required <= set(pred.columns):
                continue
            pred["scan_time_utc"]=pd.to_datetime(pred["scan_time_utc"],utc=True,errors="coerce")
            for _,rr in pred.dropna(subset=["scan_time_utc"]).iterrows():
                key=(str(rr.get("case_id")),str(rr.get("radar_site")),str(rr.get("object_id")),rr["scan_time_utc"].isoformat())
                research_probabilities.setdefault(key,{})[f"{horizon}min"]=clean(rr.get("oof_probability"))
    if args.model_summary:
        model_path=Path(args.model_summary)
        if model_path.exists():
            model_summary=json.loads(model_path.read_text(encoding="utf-8"))
            (data_dir/"model_summary.json").write_text(json.dumps(model_summary,indent=2)+"\n",encoding="utf-8")

    replay_probabilities={}
    replay_scored_rows=0
    if args.replay_dir:
        replay_root=Path(args.replay_dir)
        for path in sorted(replay_root.glob("*.geojson")):
            try:
                payload=json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for feature in payload.get("features",[]) or []:
                props=feature.get("properties") or {}
                ts=props.get("timestamp") or payload.get("metadata",{}).get("scan_time_utc")
                if not ts:
                    continue
                obj_id=props.get("object_id")
                if obj_id is None:
                    obj_id=props.get("track_id")
                rp=props.get("research_probabilities") or {}
                if rp:
                    replay_probabilities[(str(props.get("radar_site")),str(obj_id),str(ts))]=rp
                    replay_scored_rows += 1

    catalog=[]
    for (case_id,radar_site),group in objects.groupby(["case_id","radar_site"],sort=True):
        group=group.sort_values(["scan_time_utc","object_id"])
        features=[]
        for _,row in group.iterrows():
            geom_text=row.get("geometry_wkt")
            if not isinstance(geom_text,str) or not geom_text:
                continue
            try:
                geom=mapping(wkt.loads(geom_text))
            except Exception:
                continue
            props=object_properties(row, research_probabilities)
            replay_key=(str(row.get("radar_site")),str(row.get("object_id")),row["scan_time_utc"].isoformat())
            if replay_key in replay_probabilities:
                props["research_probabilities"]=replay_probabilities[replay_key]
                props["research_probability_source"]="historical_live_scorer"
                props["research_probability_policy"]="same_live_processor_causal_replay"
            features.append({"type":"Feature","geometry":geom,"properties":props})
        if not features:
            continue

        case_rows=cases[cases["case_id"].astype(str)==str(case_id)]
        case=case_rows.iloc[0].to_dict() if not case_rows.empty else {}
        times=sorted({f["properties"]["timestamp"] for f in features})
        tracks=sorted({f["properties"]["track_key"] for f in features})
        filename=f"{safe_name(case_id,radar_site)}.geojson"
        (cases_dir/filename).write_text(
            json.dumps({"type":"FeatureCollection","features":features},indent=2),
            encoding="utf-8",
        )
        radar_frames,radar_bounds=read_frames(frames_root,str(case_id),str(radar_site))

        catalog.append({
            "case_id":str(case_id),
            "radar_site":str(radar_site),
            "file":f"cases/{filename}",
            "event_start_utc":clean(case.get("event_start_utc")),
            "observing_station":clean(case.get("observing_station")),
            "peak_wind_kt":clean(case.get("peak_wind_kt")),
            "min_visibility_km":clean(case.get("min_visibility_km")),
            "hybrid_case":clean(case.get("hybrid_case")),
            "source_study":clean(case.get("source_study")),
            "scan_count":len(times),
            "track_count":len(tracks),
            "first_scan_utc":times[0],
            "last_scan_utc":times[-1],
            "radar_frames":radar_frames,
            "radar_bounds":radar_bounds,
            "status":"historical_pilot",
        })

    catalog.sort(key=lambda x:(x["event_start_utc"] or "",x["case_id"],x["radar_site"]))
    (data_dir/"catalog.json").write_text(json.dumps({
        "product":"BTV Snow Squall Historical Object Viewer",
        "build_time_utc": datetime.now(timezone.utc).isoformat(),
        "build_commit": os.environ.get("GITHUB_SHA"),
        "source_dataset_status": "QC-gated research pilot",
        "source_object_rows": int(len(objects)),
        "version":"0.3-pilot",
        "data_status":"research_pilot",
        "probability_status":"research_candidate_scored" if replay_scored_rows else "not_scored",
        "model_diagnostics_status": "research_only" if model_summary else "not_available",
        "model_summary_file": "model_summary.json" if model_summary else None,
        "truth_note":"Historical case context is not final object-level event truth.",
        "future_information_policy":"Viewer may display historical outcome context, but model predictors remain separate from future labels.",
        "radar_note":"Radar imagery is reconstructed from archived Level-II reflectivity and is shown as a historical diagnostic background.",
        "model_summary": model_summary,
        "research_probability_status": "historical_live_scorer_replay" if replay_scored_rows else ("oof_research_only" if research_probabilities else "not_available"),
        "historical_live_scorer_scored_object_scans": int(replay_scored_rows),
        "cases":catalog,
    },indent=2),encoding="utf-8")
    print(f"Built viewer package: {len(catalog)} case/radar datasets; {len(objects)} source object rows")

if __name__=="__main__":
    main()
