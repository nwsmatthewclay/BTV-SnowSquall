#!/usr/bin/env python3
"""Harvest NWS Snow Squall Warning VTEC events from the IEM archive."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
BASE="https://mesonet.agron.iastate.edu/json/vtec_events.py"
def fetch(year,wfo):
    params={"year":str(year),"wfo":wfo,"phenomena":"SQ","significance":"W"}
    req=Request(f"{BASE}?{urlencode(params)}",headers={"User-Agent":"BTV-SnowSquall historical research"})
    with urlopen(req,timeout=30) as resp: payload=json.load(resp)
    if isinstance(payload,dict):
        for key in ("events","data","results","features"):
            value=payload.get(key)
            if isinstance(value,list):
                return [x.get("properties",x) if isinstance(x,dict) else {} for x in value]
    if isinstance(payload,list): return [x.get("properties",x) if isinstance(x,dict) else {} for x in payload]
    raise ValueError("Unsupported IEM response format")
def get(row,*keys):
    for key in keys:
        if key in row and row[key] is not None:return str(row[key])
    return ""
def main():
    p=argparse.ArgumentParser();p.add_argument("--start-year",type=int,default=2018);p.add_argument("--end-year",type=int,default=2026);p.add_argument("--wfo",default="BTV");p.add_argument("--output",default="data/historical/sqw_warning_inventory.csv");a=p.parse_args()
    rows=[]
    for year in range(a.start_year,a.end_year+1):
        for row in fetch(year,a.wfo):
            rows.append({"wfo":a.wfo,"year":str(year),"phenomena":get(row,"phenom","phenomena"),"significance":get(row,"sig","significance"),"etn":get(row,"etn","eventid","event_id"),"issued":get(row,"issued"),"expired":get(row,"expired","expire"),"init_issued":get(row,"init_iss","init_issued"),"init_expired":get(row,"init_exp","init_expired"),"product_id":get(row,"prod_id","product_id"),"status":get(row,"status")})
    rows.sort(key=lambda r:(r["issued"],r["etn"]))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    fields=["wfo","year","phenomena","significance","etn","issued","expired","init_issued","init_expired","product_id","status"]
    with out.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(f"Wrote {len(rows)} Snow Squall Warning records to {out}")
if __name__=="__main__":main()
