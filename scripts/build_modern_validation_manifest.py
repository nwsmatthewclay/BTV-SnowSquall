"""Normalize the protected modern validation manifest for radar reconstruction."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

def build(source: Path, output: Path, radar_output: Path):
    d=pd.read_csv(source)
    d=d[d['reconstruction_eligible'].astype(str).str.lower().eq('true')].copy()
    if 'event_anchor_utc' in d:
        anchor=pd.to_datetime(d['event_anchor_utc'],utc=True,errors='coerce',format='mixed')
    else:
        anchor=pd.NaT
    event_date=pd.to_datetime(d['event_date_utc'],utc=True,errors='coerce',format='mixed')
    window_start=pd.to_datetime(d['analysis_window_start_utc'],utc=True,errors='coerce',format='mixed')
    anchor_source=pd.Series('case_anchor',index=d.index,dtype='object')
    anchor_source=anchor_source.mask(anchor.isna() & window_start.notna(),'validation_window_start')
    anchor=anchor.where(anchor.notna(),window_start)
    anchor=anchor.where(anchor.notna(),event_date)
    anchor_source=anchor_source.mask(anchor.isna() & event_date.notna(),'event_date_fallback')
    d['event_start_utc']=anchor.dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    d['anchor_source']=anchor_source
    d['source_study']=d['evidence_source'].astype(str)
    d['peak_wind_kt']=pd.to_numeric(d.get('wind_gust_kt'),errors='coerce')
    d['min_visibility_km']=pd.to_numeric(d.get('visibility_miles'),errors='coerce')*1.609344
    d['hybrid_case']=False
    d['observing_station']=d['observing_station'].astype(str)
    case_cols=['case_id','event_start_utc','event_anchor_utc','source_study','observing_station','peak_wind_kt','min_visibility_km','hybrid_case','analysis_window_start_utc','analysis_window_end_utc']
    for c in case_cols:
        if c not in d: d[c]=pd.NA
    d[case_cols].to_csv(output,index=False)
    radar=d[['case_id','radar_site','analysis_window_start_utc','analysis_window_end_utc','event_start_utc','truth_role','independence_status']].copy()
    radar=radar.rename(columns={'analysis_window_start_utc':'window_start_utc','analysis_window_end_utc':'window_end_utc'})
    radar['window_center_utc']=radar['event_start_utc']
    radar['source']='modern_independent_validation'
    radar.to_csv(radar_output,index=False)
    print(f'Wrote {len(d)} modern validation cases and {len(radar)} radar windows')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--radar-output',required=True)
    a=p.parse_args()
    build(Path(a.input),Path(a.output),Path(a.radar_output))

if __name__=='__main__':
    main()
