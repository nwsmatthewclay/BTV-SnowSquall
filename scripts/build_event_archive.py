"""Build a synchronized historical snow-squall radar + environment archive.

Every selected case/radar scan gets a compact gridded NPZ, reflectivity PNG,
base-velocity PNG, scan metadata, and a synchronized NARR/RUC/RAP environment
snapshot containing the repository's CAPE/SNSQ/etc diagnostics.

Raw Level-II remains the source-of-truth; this is the portable analysis layer.
"""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.environment import acquire_for_radar_time, extract_features, environment_cache_key
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep
from processing.radar_sites import apply_radar_origin, radar_origin_for_site

FILENAME_RE=re.compile(r"^(?P<radar>K[A-Z0-9]{3})(?P<stamp>\d{8}_\d{6})(?:_.*|\.gz)$")
ENV_FIELDS=("snsq","snsq_status","moisture_factor","instability_factor","wind_factor","snow_temperature_pass",
"cape_jkg","mucape_jkg","mlcape_jkg","cin_jkg","mucin_jkg","mlcin_jkg","dcape_jkg","pwat_mm",
"lcl_m","srh01_m2s2","srh03_m2s2","shear_0_6km_ms","shear_0_6km_kt","rh_2m_pct",
"temperature_2m_k","dewpoint_2m_k","wet_bulb_2m_c","rh_0_2km_pct","wind_0_1km_kt","wind_0_3km_kt",
"shear_0_1km_kt","shear_0_3km_kt","lapse_rate_0_3km_c_km","lapse_rate_0_7_5km_c_km",
"wet_bulb_0_3km_c","frontogenesis","dcva","omega","epv","cloud_layer_depth_m",
"cloud_layer_rh_pct","cloud_layer_mean_wind_kt","cloud_layer_shear_kt")
STATION_COORDS={"KBTV":(44.471955,-73.153276),"KMPV":(44.203489,-72.562096),"KMSS":(44.936241,-74.845120)}

def parse_utc(v):
    return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)

def file_time(path):
    m=FILENAME_RE.match(path.name)
    return datetime.strptime(m.group("stamp"),"%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc) if m else None

def normalize_coord(row):
    for a,b in (("case_lat","case_lon"),("lat","lon")):
        lat=pd.to_numeric(pd.Series([row.get(a)]),errors="coerce").iloc[0]
        lon=pd.to_numeric(pd.Series([row.get(b)]),errors="coerce").iloc[0]
        if pd.notna(lat) and pd.notna(lon): return float(lat),float(lon)
    return STATION_COORDS.get(str(row.get("observing_station") or "").upper(),(None,None))

def save_png(lon,lat,data,title,out,vmin,vmax,cmap,label):
    fig,ax=plt.subplots(figsize=(8.5,7),dpi=120)
    valid=np.isfinite(data)
    if valid.any():
        m=ax.pcolormesh(lon,lat,data,shading="auto",cmap=cmap,vmin=vmin,vmax=vmax)
        cb=fig.colorbar(m,ax=ax,pad=0.02); cb.ax.set_ylabel(label)
    else:
        ax.text(.5,.5,"No valid data",ha="center",va="center",transform=ax.transAxes)
    ax.set_title(title); ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.grid(alpha=.25)
    fig.tight_layout(); out.parent.mkdir(parents=True,exist_ok=True); fig.savefig(out); plt.close(fig)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cases",required=True); ap.add_argument("--raw-root",required=True)
    ap.add_argument("--output-dir",required=True); ap.add_argument("--rap-dir",default="data/raw/RAP_event_archive")
    ap.add_argument("--ruc-dir",default="data/raw/RUC_event_archive"); args=ap.parse_args()
    cases=pd.read_csv(args.cases)
    lookup={}
    for _,r in cases.iterrows(): lookup[str(r.get("case_id") or r.get("candidate_id"))]=r
    links=[]
    raw=Path(args.raw_root)
    for case_id,case in lookup.items():
        start=pd.to_datetime(case.get("window_start_utc"),utc=True,errors="coerce")
        end=pd.to_datetime(case.get("window_end_utc"),utc=True,errors="coerce")
        if pd.isna(start) or pd.isna(end):
            ev=pd.to_datetime(case.get("event_start_utc"),utc=True,errors="coerce")
            start=ev-pd.Timedelta(minutes=90); end=ev+pd.Timedelta(minutes=90)
        for radar in ("KCXX","KTYX"):
            rr=raw/radar
            if not rr.exists(): continue
            for p in rr.rglob("*"):
                if not p.is_file(): continue
                ts=file_time(p)
                if ts is None or ts<start.to_pydatetime() or ts>end.to_pydatetime(): continue
                links.append({"case_id":case_id,"radar_site":radar,"source_file":str(p),
                              "scan_time_utc":ts.isoformat(),"event_start_utc":pd.to_datetime(case.event_start_utc,utc=True).isoformat()})
    links=pd.DataFrame(links).drop_duplicates(["case_id","radar_site","source_file"])
    if links.empty: raise SystemExit("No radar scans matched case windows.")
    root=Path(args.output_dir); root.mkdir(parents=True,exist_ok=True)
    env_cache={}; scan_rows=[]; unique=links.drop_duplicates(["radar_site","source_file"])
    print(f"Cases={len(lookup)} case-scan-links={len(links)} unique-radar-volumes={len(unique)}")
    for n,(_,s) in enumerate(unique.iterrows(),1):
        case=lookup[str(s.case_id)]; ts=parse_utc(s.scan_time_utc); radar=str(s.radar_site)
        product=root/"scans"/radar/ts.strftime("%Y%m%d")/ts.strftime("%Y%m%d_%H%M%S")
        product.mkdir(parents=True,exist_ok=True); status="ok"; error=""; fields={}
        try:
            r=read_level2(Path(s.source_file)); origin=radar_origin_for_site(radar); apply_radar_origin(r,origin)
            fields=resolve_fields(r)
            wanted=[fields[k] for k in ("reflectivity","velocity","spectrum_width","zdr","rhohv","kdp") if fields.get(k)]
            if not fields.get("reflectivity"): raise RuntimeError("reflectivity_field_unavailable")
            grid=grid_lowest_sweep(r,wanted,origin_lat=origin[0],origin_lon=origin[1],grid_size_km=180,spacing_km=1)
            lat,lon=grid_latlon(grid); refl=grid_field_2d(grid,fields["reflectivity"])
            velms=grid_field_2d(grid,fields["velocity"]) if fields.get("velocity") else np.full_like(refl,np.nan)
            arrays={"latitude":lat.astype("float32"),"longitude":lon.astype("float32"),
                    "reflectivity_dbz":refl.astype("float32"),"base_velocity_ms":velms.astype("float32"),
                    "base_velocity_kt":(velms*1.94384449244).astype("float32")}
            aliases={"spectrum_width":"spectrum_width_ms","zdr":"zdr_db","rhohv":"rhohv","kdp":"kdp_degkm"}
            for canon,name in aliases.items():
                if fields.get(canon): arrays[name]=grid_field_2d(grid,fields[canon]).astype("float32")
            np.savez_compressed(product/"radar_fields.npz",**arrays)
            save_png(lon,lat,refl,f"{radar} {ts:%Y-%m-%d %H:%MZ} Reflectivity",product/"reflectivity.png",0,70,"turbo","dBZ")
            save_png(lon,lat,velms*1.94384449244,f"{radar} {ts:%Y-%m-%d %H:%MZ} Base Velocity",product/"base_velocity.png",-80,80,"RdBu_r","kt")
            meta=volume_metadata(r,Path(s.source_file))
            (product/"metadata.json").write_text(json.dumps({
                "archive_version":"event_radar_environment_v1","case_id":str(s.case_id),"radar_site":radar,
                "scan_time_utc":s.scan_time_utc,"event_start_utc":s.event_start_utc,
                "minutes_from_event_start":(ts-parse_utc(s.event_start_utc)).total_seconds()/60,
                "raw_level2":str(s.source_file),"reader_backend":meta.get("reader_backend"),
                "source_fields":meta.get("fields",[]),"has_reflectivity":True,
                "has_base_velocity":bool(fields.get("velocity"))},indent=2)+"\n",encoding="utf-8")
        except Exception as exc:
            status="error"; error=f"{type(exc).__name__}: {exc}"
            (product/"metadata.json").write_text(json.dumps({"archive_version":"event_radar_environment_v1",
                "case_id":str(s.case_id),"radar_site":radar,"scan_time_utc":s.scan_time_utc,
                "raw_level2":str(s.source_file),"status":"error","error":error},indent=2)+"\n",encoding="utf-8")
        case_env=build_env(lookup[str(s.case_id)],ts,Path(args.rap_dir),Path(args.ruc_dir),env_cache)
        scan_rows.append({"case_id":str(s.case_id),"radar_site":radar,"scan_time_utc":s.scan_time_utc,
            "event_start_utc":s.event_start_utc,"source_file":str(s.source_file),
            "archive_path":str(product.relative_to(root)),"radar_archive_status":status,"radar_archive_error":error,
            "minutes_from_event_start":(ts-parse_utc(s.event_start_utc)).total_seconds()/60,**case_env})
        if n%25==0 or n==len(unique): print(f"Archived {n}/{len(unique)}")
    manifest=pd.DataFrame(scan_rows); manifest.to_csv(root/"event_scan_manifest.csv",index=False)
    manifest.sort_values(["case_id","scan_time_utc"]).to_csv(root/"event_environment_timeseries.csv",index=False)
    qc=[]
    for case_id,g in manifest.groupby("case_id",dropna=False):
        qc.append({"case_id":case_id,"radar_sites":",".join(sorted(g.radar_site.unique())),
                   "scan_count":len(g),"successful_radar_scans":int((g.radar_archive_status=="ok").sum()),
                   "radar_failures":int((g.radar_archive_status!="ok").sum()),
                   "environment_complete":int((g.environment_status=="complete").sum()),
                   "environment_partial":int((g.environment_status=="partial").sum()),
                   "environment_unavailable_or_error":int((~g.environment_status.isin(["complete","partial"])).sum())})
    pd.DataFrame(qc).to_csv(root/"event_archive_qc.csv",index=False)
    summary={"archive_version":"event_radar_environment_v1","cases":len(lookup),"case_scan_links":len(links),
              "unique_radar_volumes":len(unique),"successful_radar_archives":int((manifest.radar_archive_status=="ok").sum()),
              "radar_failures":int((manifest.radar_archive_status!="ok").sum()),
              "environment_complete":int((manifest.environment_status=="complete").sum()),
              "environment_partial":int((manifest.environment_status=="partial").sum()),
              "environment_unavailable_or_error":int((~manifest.environment_status.isin(["complete","partial"])).sum()),
              "required_radar_fields":["reflectivity","base_velocity"],"environment_fields":list(ENV_FIELDS)}
    (root/"archive_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))

def build_env(case,ts,rap_dir,ruc_dir,cache):
    lat,lon=normalize_coord(case)
    if lat is None or lon is None: return {"environment_status":"unavailable","environment_error":"missing_case_coordinates"}
    key=environment_cache_key(ts)
    if key not in cache:
        try: cache[key]=acquire_for_radar_time(ts,rap_dir=rap_dir,ruc_dir=ruc_dir,max_age_minutes=180)
        except Exception as exc: cache[key]=("ERROR",type(exc).__name__,str(exc))
    acquired=cache[key]
    if acquired is None: return {"environment_status":"unavailable"}
    if acquired and acquired[0]=="ERROR": return {"environment_status":"error","environment_error":acquired[2]}
    provider,match,path=acquired
    try:
        env=extract_features(provider,path,lat,lon,ts,expected_valid_time=match.valid_time)
        fields=env.get("fields") or {}
        out={"environment_status":env.get("status","partial"),"environment_source":provider,
             "environment_valid_time_utc":env.get("source_valid_time_utc"),"environment_age_minutes":env.get("age_minutes"),
             "environment_match_method":"latest_valid_analysis_at_or_before_scan",
             "environment_missing_fields":";".join(env.get("missing_fields") or [])}
        out.update({k:fields.get(k) for k in ENV_FIELDS if k != "snsq_status"})
        if "snsq_status" in fields:
            out["snsq_status"] = fields.get("snsq_status")
        elif provider == "RAP":
            out["snsq_status"] = "not_reported_by_extractor"
        else:
            out["snsq_status"] = "historical_profile_extension_pending"
        return out
    except Exception as exc: return {"environment_status":"error","environment_error":f"{type(exc).__name__}: {exc}"}

if __name__=="__main__": main()
