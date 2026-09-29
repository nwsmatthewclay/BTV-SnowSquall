"""Harvest BTV-domain IEM Local Storm Reports with correct epoch-time parsing."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = 'https://mesonet.agron.iastate.edu/cgi-bin/request/gis/lsr.py'
SNOW_RE = re.compile(r'\b(?:snow\s+squall|white[- ]?out|near[- ]?zero\s+(?:vis|visibility)|blinding\s+snow)\b', re.I)

def request(url, **kwargs):
    for attempt in range(4):
        try:
            r=requests.get(url,timeout=120,**kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt==3: raise
    raise RuntimeError('unreachable')

def norm_county(value):
    text=str(value or '').upper().strip()
    text=re.sub(r'[^A-Z0-9 ]+',' ',text)
    text=re.sub(r'\b(COUNTY|PARISH|BOROUGH|CENSUS AREA)\b','',text)
    return re.sub(r'\s+',' ',text).strip()

def parse_valid(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None

    # Some IEM exports use compact calendar stamps instead of Unix time.
    digits = text.lstrip('-').split('.')[0]
    if digits.isdigit() and len(digits) in (12, 14):
        try:
            fmt = '%Y%m%d%H%M%S' if len(digits) == 14 else '%Y%m%d%H%M'
            ts = pd.Timestamp.strptime(digits, fmt).tz_localize('UTC')
            if 1900 <= ts.year <= 2100:
                return ts
        except (TypeError, ValueError):
            pass

    try:
        numeric = float(text)
        magnitude = abs(numeric)
        if magnitude >= 1e15:
            unit = 'us'
        elif magnitude >= 1e11:
            unit = 'ms'
        elif magnitude >= 1e9:
            unit = 's'
        else:
            unit = None
        if unit is not None:
            ts = pd.to_datetime(numeric, unit=unit, utc=True, errors='coerce')
        else:
            ts = pd.to_datetime(text, utc=True, errors='coerce', format='mixed')
    except (TypeError, ValueError, OverflowError):
        ts = pd.to_datetime(text, utc=True, errors='coerce', format='mixed')
    if pd.isna(ts):
        return None
    if not 1900 <= ts.year <= 2100:
        return None
    return ts
def distance_km(lat1,lon1,lat2,lon2):
    from math import asin,cos,radians,sin,sqrt
    if None in (lat1,lon1,lat2,lon2): return None
    p1,p2=radians(float(lat1)),radians(float(lat2))
    dp=radians(float(lat2)-float(lat1)); dl=radians(float(lon2)-float(lon1))
    a=sin(dp/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
    return 6371.0*2*asin(min(1.0,sqrt(a)))

def case_id(ts,lat,lon,idx):
    raw=f'{ts.isoformat()}|{lat}|{lon}|{idx}'
    return f'IEMLSR{ts:%Y%m%d%H%M}_{hashlib.sha1(raw.encode()).hexdigest()[:10]}'

def harvest(start_year,end_year):
    rows=[]
    for year in range(start_year,end_year+1):
        for state in ('VT','NY'):
            print(f'IEM LSR {year} {state}')
            params={'state':state,'sts':f'{year}-01-01T00:00Z','ets':f'{year}-12-31T23:59Z','fmt':'csv'}
            try:
                text=request(BASE,params=params).text
                frame=pd.read_csv(io.StringIO(text)) if text.strip() else pd.DataFrame()
            except Exception as exc:
                print(f'  unavailable: {exc}')
                continue
            if frame.empty: continue
            remarks=frame.get('REMARK',pd.Series('',index=frame.index)).fillna('').astype(str)
            types=frame.get('TYPETEXT',pd.Series('',index=frame.index)).fillna('').astype(str)
            mask=(remarks+' '+types).str.contains(SNOW_RE,na=False)
            for idx,row in frame[mask].iterrows():
                county=norm_county(row.get('COUNTY',''))
                if state=='VT' and county in {'BENNINGTON','WINDHAM'}: continue
                if state=='NY' and county not in {'CLINTON','ESSEX','FRANKLIN','ST LAWRENCE'}: continue
                ts=parse_valid(row.get('VALID'))
                if ts is None: continue
                lat=pd.to_numeric(row.get('LAT'),errors='coerce'); lon=pd.to_numeric(row.get('LON'),errors='coerce')
                lat=None if pd.isna(lat) else float(lat); lon=None if pd.isna(lon) else float(lon)
                rows.append({
                    'candidate_id':case_id(ts,lat,lon,idx),
                    'candidate_source':'IEM_LSR',
                    'verification_class':'unverified_report_only',
                    'verification_status':'unverified_candidate',
                    'event_start_utc':ts.isoformat(),
                    'state':state,'county':county,'lat':lat,'lon':lon,
                    'event_type':str(row.get('TYPETEXT','') or ''),
                    'source':str(row.get('SOURCE','') or ''),
                    'wfo':str(row.get('WFO','') or ''),
                    'city':str(row.get('CITY','') or ''),
                    'narrative':str(row.get('REMARK','') or '').strip(),
                    'evidence':'iem_lsr_text',
                })
    return pd.DataFrame(rows)

def cluster(frame):
    if frame.empty: return frame.copy()
    ordered=frame.sort_values('event_start_utc').copy()
    ordered['event_dt']=pd.to_datetime(ordered['event_start_utc'],utc=True,format='mixed')
    clusters=[]
    for _,row in ordered.iterrows():
        assigned=None
        for cluster in reversed(clusters[-100:]):
            gap=(row['event_dt']-cluster['last_time']).total_seconds()/60
            if gap>60: break
            dist=distance_km(row['lat'],row['lon'],cluster['lat'],cluster['lon'])
            if dist is not None and dist<=75:
                assigned=cluster; break
        if assigned is None:
            clusters.append({'cluster_id':len(clusters)+1,'first_time':row['event_dt'],'last_time':row['event_dt'],'lat':row['lat'],'lon':row['lon'],'rows':[row]})
        else:
            assigned['last_time']=max(assigned['last_time'],row['event_dt'])
            assigned['rows'].append(row)
    out=[]
    for c in clusters:
        rows=c['rows']; first=min(r['event_dt'] for r in rows)
        out.append({
            'cluster_id':f'IEMCL{first:%Y%m%d%H%M}_{c["cluster_id"]:04d}',
            'event_start_utc':first.isoformat(),
            'event_end_utc':max(r['event_dt'] for r in rows).isoformat(),
            'report_count':len(rows),
            'state':rows[0]['state'],'county':rows[0]['county'],'lat':rows[0]['lat'],'lon':rows[0]['lon'],
            'cities':'; '.join(sorted({str(r['city']) for r in rows if str(r['city']).strip()})),
            'narratives':' || '.join(str(r['narrative']) for r in rows[:8]),
            'candidate_ids':';'.join(str(r['candidate_id']) for r in rows),
        })
    return pd.DataFrame(out)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--start-year',type=int,default=2002); parser.add_argument('--end-year',type=int,default=2026); parser.add_argument('--output-dir',required=True)
    args=parser.parse_args(); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    reports=harvest(args.start_year,args.end_year); clusters=cluster(reports)
    reports.to_csv(out/'iem_lsr_reports.csv',index=False); clusters.to_csv(out/'iem_lsr_case_clusters.csv',index=False)
    summary={'raw_reports':len(reports),'clusters':len(clusters),'years':f'{args.start_year}-{args.end_year}','timestamp_policy':'IEM VALID numeric timestamps are interpreted as Unix seconds unless millisecond-scale.','training_policy':'unverified_report_only; never training truth without independent verification.'}
    (out/'iem_lsr_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8'); print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
