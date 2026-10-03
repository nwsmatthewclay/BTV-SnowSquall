"""Replay the live shadow scorer over historical object scans."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from scripts.live_model_features import build_live_feature_frame, feature_coverage
from scripts.add_national_pretraining_features import augment as augment_national_pretraining
from scripts.model_runtime import ModelRuntime
from scripts.probability_postprocess import monotone_cumulative_probabilities

HORIZONS=(15,30,45,60)
MIN_FEATURE_COVERAGE=0.40
MIN_INSTANTANEOUS_FEATURES={"max_reflectivity_dbz","mean_reflectivity_dbz","area_km2","length_km","width_km","core_pixel_count","bbox_aspect_ratio","reflectivity_gradient_p90_dbkm","gradient_fraction_above_5dbkm","background_reflectivity_dbz","reflectivity_contrast_db"}

def read_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): return default

def flatten(props):
    row=dict(props)
    env=props.get("environment") or {}
    if isinstance(env,dict):
        for k,v in env.items():
            row[k]=v.get("value") if isinstance(v,dict) and "value" in v else v
    return row

def runtimes(root):
    out={}; info={}
    for h in HORIZONS:
        dirs=[root/f"candidate_ensemble_refresh_{h}m",root/f"candidate_ensemble_expansion_{h}m",root/f"baseline_refresh_{h}m",root/f"baseline_expansion_{h}m"]
        d=next((x for x in dirs if (x/"metrics.json").exists()),None)
        rt=ModelRuntime.load(d) if d else ModelRuntime()
        out[h]=rt
        info[str(h)]={"model_present":rt.model is not None,"selected_artifact":d.name if d else None,"model_version":rt.metadata.get("model_version"),"predictor_count":len(rt.feature_columns)}
    return out,info

def score_case(path,model_root):
    payload=read_json(path,{})
    tracks={}
    for f in payload.get("features") or []:
        p=f.get("properties") or {}
        tid=p.get("track_key") or p.get("track_id")
        if tid is not None: tracks.setdefault(str(tid),[]).append(f)
    rts,info=runtimes(model_root); scored=errors=0
    for tid,fs in tracks.items():
        fs.sort(key=lambda f:str((f.get("properties") or {}).get("timestamp","")))
        history=[]
        for f in fs:
            p=f.setdefault("properties",{})
            cur=flatten(p); cur["track_id"]=p.get("track_id",tid); history.append(cur)
            frame=build_live_feature_frame(history,cur["track_id"])
            frame,national=augment_national_pretraining(frame,model_root)
            raw={}; cov={}; errs={}
            available=[c for c in MIN_INSTANTANEOUS_FEATURES if c in frame.columns and frame.tail(1)[c].notna().any()]
            for h in HORIZONS:
                rt=rts[h]; c=feature_coverage(frame.tail(1),rt.feature_columns); cov[str(h)]=c
                if c["fraction"]<MIN_FEATURE_COVERAGE: errs[str(h)]=f"low_feature_coverage:{c['fraction']:.3f}"; continue
                if len(available)<6: errs[str(h)]="insufficient_instantaneous_object_features"; continue
                try:
                    result=rt.score_candidate(frame.tail(1))
                    if result: raw[str(h)]=float(result[0])
                except Exception as exc: errs[str(h)]=f"{type(exc).__name__}: {exc}"
            projected=monotone_cumulative_probabilities(raw) if raw else {}
            p["research_probabilities"]={str(h):projected.get("cumulative",{}).get(str(h)) for h in HORIZONS}
            p["research_probabilities_raw"]=raw
            p["research_interval_probabilities"]=projected.get("interval",{}) if raw else {}
            p["research_score_metadata"]={"mode":"historical_live_shadow_replay","release_status":"candidate_only_not_operational","feature_coverage":cov,"score_errors":errs,"national_pretraining":national,"model_artifacts":info,"leakage_policy":"current_and_prior_track_scans_only"}
            if raw: scored+=1
            if errs: errors+=1
    payload.setdefault("metadata",{})["historical_live_scorer"]={"status":"scored","mode":"historical_live_shadow_replay","updated_utc":datetime.now(timezone.utc).isoformat(),"candidate_only_not_operational":True,"scored_object_scans":scored,"object_scans_with_errors":errors,"model_info":info}
    return payload,scored,errors

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input-root",type=Path,required=True); ap.add_argument("--output-root",type=Path,required=True); ap.add_argument("--model-root",type=Path,required=True); a=ap.parse_args()
    a.output_root.mkdir(parents=True,exist_ok=True); total=errs=cases=0
    for path in sorted(a.input_root.glob("*.geojson")):
        payload,n,e=score_case(path,a.model_root); (a.output_root/path.name).write_text(json.dumps(payload,separators=(",",":"))+"\\n",encoding="utf-8"); total+=n; errs+=e; cases+=1; print(path.name,"scored:",n,"errors:",e)
    summary={"status":"complete","mode":"historical_live_shadow_replay","updated_utc":datetime.now(timezone.utc).isoformat(),"cases":cases,"scored_object_scans":total,"object_scans_with_errors":errs,"candidate_only_not_operational":True}
    (a.output_root/"historical_live_scorer_summary.json").write_text(json.dumps(summary,indent=2)+"\\n",encoding="utf-8"); print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
