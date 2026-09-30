"""Score protected modern validation cases and report anchor-relative diagnostics."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.live_model_features import build_live_feature_frame, feature_coverage
from scripts.add_national_pretraining_features import augment as augment_national_pretraining
from scripts.model_runtime import ModelRuntime

HORIZONS=(15,30,45,60)
THRESHOLDS=(0.10,0.20,0.30,0.50)

def score_case(case_row, objects, model_root: Path):
    case_id=str(case_row['case_id'])
    anchor=pd.to_datetime(case_row['event_start_utc'],utc=True,errors='coerce')
    start=pd.to_datetime(case_row['analysis_window_start_utc'],utc=True,errors='coerce')
    end=pd.to_datetime(case_row['analysis_window_end_utc'],utc=True,errors='coerce')
    case_objects=objects[objects['case_id'].astype(str).eq(case_id)].copy()
    results=[]
    for track_id, group in case_objects.groupby('object_id',sort=False):
        history=[]
        for row in group.to_dict(orient='records'):
            item=dict(row)
            item['track_id']=str(track_id)
            item['timestamp']=row.get('scan_time_utc')
            history.append(item)
        frame=build_live_feature_frame(history,track_id)
        frame, national_prior=augment_national_pretraining(frame, model_root)
        if frame.empty: continue
        base={}
        for h in HORIZONS:
            runtime=ModelRuntime.load(model_root/f'candidate_ensemble_expansion_{h}m')
            vals=[]
            for row_idx, feature_row in frame.iterrows():
                coverage=feature_coverage(frame.loc[[row_idx]],runtime.feature_columns)
                if runtime.model is None or coverage['fraction']<0.80: continue
                p=float(runtime.score_candidate(frame.loc[[row_idx]])[0])
                ts=pd.to_datetime(feature_row.get('timestamp'),utc=True,errors='coerce')
                if pd.notna(ts): vals.append((ts,p))
            inside=[p for t,p in vals if pd.notna(start) and pd.notna(end) and start<=t<=end]
            pre=[p for t,p in vals if pd.notna(anchor) and t<anchor]
            max_in_window[str(h)]=max(inside) if inside else None
            max_pre[str(h)]=max(pre) if pre else None
            crosses={}
            for threshold in THRESHOLDS:
                hits=[t for t,p in vals if p>=threshold and pd.notna(anchor) and t<=anchor]
                crosses[str(threshold)]=hits[0].isoformat() if hits else None
            first_cross[str(h)]=crosses
        results.append({'case_id':case_id,'object_id':str(track_id),'anchor_utc':anchor.isoformat() if pd.notna(anchor) else None,'analysis_window_start_utc':start.isoformat() if pd.notna(start) else None,'analysis_window_end_utc':end.isoformat() if pd.notna(end) else None,'current_score':base,'max_probability_in_window':max_in_window,'max_probability_pre_anchor':max_pre,'first_threshold_crossing_before_anchor':first_cross})
    return results

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cases',required=True)
    p.add_argument('--objects',required=True)
    p.add_argument('--model-root',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    cases=pd.read_csv(a.cases)
    objects=pd.read_csv(a.objects)
    output={'validation_status':'anchor_relative_research_diagnostic','cases':[]}
    for _, row in cases.iterrows():
        output['cases'].extend(score_case(row,objects,Path(a.model_root)))
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'objects_scored':len(output['cases']),'status':output['validation_status']},indent=2))

if __name__=='__main__':
    main()
