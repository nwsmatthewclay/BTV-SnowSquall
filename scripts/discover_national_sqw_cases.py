"""Harvest a national Snow Squall Warning inventory from IEM COW.

The output is a weakly supervised research reservoir, not ground truth.
Warning issuance, IEM verification, and LSR linkage are retained as separate
fields so later radar/surface review can promote cases into stronger labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = "https://mesonet.agron.iastate.edu/api/1/cow.json"

def request(params):
    last=None
    for attempt in range(4):
        try:
            r=requests.get(BASE,params=params,timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last=exc
            if attempt<3:
                import time; time.sleep(2**attempt)
    raise RuntimeError(str(last))

def finite(v):
    try:
        x=float(v)
        return x if pd.notna(x) else None
    except (TypeError,ValueError):
        return None

def case_key(props):
    issue=str(props.get('issue') or '')
    wfo=str(props.get('wfo') or '')
    eventid=str(props.get('eventid') or '')
    raw=f'{issue}|{wfo}|{eventid}'
    digest=hashlib.sha1(raw.encode()).hexdigest()[:10]
    try:
        dt=pd.to_datetime(issue,utc=True).to_pydatetime()
        stamp=dt.strftime('%Y%m%d%H%M')
    except Exception:
        stamp='UNKNOWN'
    return f'NSQW{stamp}_{digest}'

def month_ranges(start_year,end_year):
    for y in range(start_year,end_year+1):
        for m in range(1,13):
            start=pd.Timestamp(year=y,month=m,day=1,tz='UTC')
            end=(start+pd.offsets.MonthBegin(1))-pd.Timedelta(seconds=1)
            yield start,end

def harvest(start_year,end_year):
    rows=[]; seen=set()
    for start,end in month_ranges(start_year,end_year):
        params={'begints':start.isoformat().replace('+00:00','Z'),'endts':end.isoformat().replace('+00:00','Z'),'phenomena':'SQ'}
        print(f'IEM COW SQW {start:%Y-%m}')
        try:
            payload=request(params)
        except Exception as exc:
            print('  unavailable:',exc)
            continue
        features=((payload.get('events') or {}).get('features') or [])
        for feature in features:
            props=feature.get('properties') or {}
            if str(props.get('phenomena') or 'SQ').upper()!='SQ':
                continue
            issue=pd.to_datetime(props.get('issue'),utc=True,errors='coerce')
            if pd.isna(issue):
                continue
            cid=case_key(props)
            if cid in seen: continue
            seen.add(cid)
            all_ids=str(props.get('stormreports_all') or '').strip()
            verify_ids=str(props.get('stormreports') or '').strip()
            all_count=len([x for x in all_ids.split(',') if x.strip()])
            verify_count=len([x for x in verify_ids.split(',') if x.strip()])
            rows.append({
                'case_id':cid,
                'warning_issue_utc':issue.isoformat(),
                'warning_expire_utc':props.get('expire'),
                'wfo':str(props.get('wfo') or ''),
                'event_id':str(props.get('eventid') or ''),
                'lat':finite(props.get('lat0')),
                'lon':finite(props.get('lon0')),
                'iem_verified':bool(props.get('verify')),
                'first_verifying_lsr_lead_min':finite(props.get('lead0')),
                'verifying_lsr_count':verify_count,
                'all_in_buffer_lsr_count':all_count,
                'warning_status':str(props.get('status') or ''),
                'warning_area_km2':finite(props.get('parea')),
                'warning_perimeter_km':finite(props.get('perimeter')),
                'warning_vtec':'SQ-W',
                'evidence_source':'IEM_COW_SQW',
                'supervision_class':'warning_verified' if bool(props.get('verify')) else 'warning_only',
            })
    return pd.DataFrame(rows)

def cluster(frame):
    if frame.empty: return frame.copy()
    d=frame.copy(); d['dt']=pd.to_datetime(d.warning_issue_utc,utc=True)
    d=d.sort_values('dt').reset_index(drop=True)
    groups=[]
    for _,r in d.iterrows():
        assigned=None
        for g in reversed(groups[-100:]):
            gap=(r['dt']-g['last']).total_seconds()/60
            if gap>90: break
            if str(r['wfo'])!=str(g['wfo']): continue
            if pd.isna(r['lat']) or pd.isna(r['lon']) or g['lat'] is None or g['lon'] is None: continue
            dlat=r['lat']-g['lat']; dlon=(r['lon']-g['lon'])
            if (dlat*dlat+dlon*dlon)**0.5 <= 1.0:
                assigned=g; break
        if assigned is None:
            groups.append({'last':r['dt'],'wfo':r['wfo'],'lat':r['lat'],'lon':r['lon'],'rows':[r]})
        else:
            assigned['last']=max(assigned['last'],r['dt']); assigned['rows'].append(r)
    out=[]
    for i,g in enumerate(groups,1):
        rs=g['rows']; first=min(r['dt'] for r in rs)
        out.append({
            'episode_id':f'NSQEP{first:%Y%m%d%H%M}_{i:05d}',
            'episode_start_utc':first.isoformat(),
            'episode_end_utc':max(r['dt'] for r in rs).isoformat(),
            'wfo':g['wfo'],'warning_count':len(rs),
            'verified_warning_count':int(sum(bool(r['iem_verified']) for r in rs)),
            'verifying_lsr_count':int(sum(int(r['verifying_lsr_count']) for r in rs)),
            'lat':g['lat'],'lon':g['lon'],
            'case_ids':';'.join(str(r['case_id']) for r in rs),
        })
    return pd.DataFrame(out)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start-year',type=int,default=2018)
    p.add_argument('--end-year',type=int,default=2026)
    p.add_argument('--output-dir',required=True)
    a=p.parse_args(); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    d=harvest(a.start_year,a.end_year); e=cluster(d)
    d.to_csv(out/'national_sqw_warnings.csv',index=False)
    e.to_csv(out/'national_sqw_episodes.csv',index=False)
    s={'warnings':len(d),'episodes':len(e),'verified_warnings':int(d.iem_verified.sum()) if not d.empty else 0,'years':f'{a.start_year}-{a.end_year}','source':'IEM COW','supervision_policy':'warning_verified is stronger evidence than warning_only, but neither is final physical-event truth without radar/surface review.'}
    (out/'national_sqw_summary.json').write_text(json.dumps(s,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(s,indent=2))

if __name__=='__main__': main()