"""Export georeferenced radar reflectivity frames grouped by historical case/radar."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.radar_grid import grid_field_2d, grid_lowest_sweep, grid_latlon

def parse_utc(value):
    return pd.to_datetime(value, utc=True, errors="coerce").to_pydatetime()

def collect_files(root):
    return [p for p in sorted(Path(root).rglob("*")) if p.is_file()]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",required=True)
    parser.add_argument("--input",required=True)
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--spacing-km",type=float,default=1.0)
    parser.add_argument("--grid-size-km",type=float,default=180.0)
    args=parser.parse_args()

    manifest=pd.read_csv(args.manifest)
    manifest["window_start"]=manifest["window_start_utc"].map(parse_utc)
    manifest["window_end"]=manifest["window_end_utc"].map(parse_utc)
    rows=manifest.dropna(subset=["window_start","window_end","case_id","radar_site"]).to_dict("records")
    root=Path(args.output_dir)
    files=collect_files(args.input)

    grouped={}
    seen=set()
    for path in files:
        try:
            radar=read_level2(path)
            meta=volume_metadata(radar,path)
            ts=pd.to_datetime(meta["scan_time_utc"], utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            ts=ts.to_pydatetime()
            radar_name=meta.get("radar_site") or path.name[:4]
            candidates=[r for r in rows if r["radar_site"]==radar_name and r["window_start"]<=ts<=r["window_end"]]
            if not candidates:
                continue
            fields=resolve_fields(radar)
            field=fields.get("reflectivity")
            if field is None:
                continue

            grid=grid_lowest_sweep(radar,field,grid_size_km=args.grid_size_km,spacing_km=args.spacing_km)
            data=grid_field_2d(grid,field)
            lat,lon=grid_latlon(grid)
            west,east=float(np.nanmin(lon)),float(np.nanmax(lon))
            south,north=float(np.nanmin(lat)),float(np.nanmax(lat))
            stamp=ts.strftime("%Y%m%dT%H%M%SZ")

            for match in candidates:
                key=(str(match["case_id"]),radar_name)
                out_dir=root/"data"/"cases"/f"{match['case_id']}_{radar_name}"/"frames"
                out_dir.mkdir(parents=True,exist_ok=True)
                out_file=out_dir/f"{stamp}.png"
                if not out_file.exists():
                    fig,ax=plt.subplots(figsize=(8,7),dpi=120)
                    ax.imshow(np.ma.masked_invalid(data),origin="lower",
                              extent=[west,east,south,north],vmin=0,vmax=60,
                              cmap="turbo",interpolation="nearest",alpha=.86)
                    ax.set_xlim(west,east); ax.set_ylim(south,north); ax.axis("off")
                    fig.subplots_adjust(0,0,1,1); fig.savefig(out_file,transparent=True,pad_inches=0)
                    plt.close(fig)
                grouped.setdefault(key,{"bounds":[[south,west],[north,east]],"frames":[]})
                rel=out_file.relative_to(root/"data").as_posix()
                item={"timestamp":ts.isoformat(),"file":rel}
                if item not in grouped[key]["frames"]:
                    grouped[key]["frames"].append(item)
                seen.add((path,key))
            print(f"{path.name}: {stamp}")
        except Exception as exc:
            print(f"SKIP {path}: {type(exc).__name__}: {exc}")

    for key,value in grouped.items():
        case_id,radar=key
        value["frames"].sort(key=lambda x:x["timestamp"])
        frame_dir=root/"data"/"cases"/f"{case_id}_{radar}"
        frame_dir.mkdir(parents=True,exist_ok=True)
        (frame_dir/"frames.json").write_text(json.dumps(value,indent=2),encoding="utf-8")

    print(f"Built {len(grouped)} case/radar frame sets with {sum(len(v['frames']) for v in grouped.values())} frames.")

if __name__=="__main__":
    main()
