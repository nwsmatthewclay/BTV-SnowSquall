"""Render compact geographic radar frames for the static object viewer."""
from __future__ import annotations
import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyart
from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.radar_grid import grid_field_2d, grid_lowest_sweep, grid_latlon

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True); p.add_argument("--output-dir",required=True)
    p.add_argument("--limit",type=int,default=0)
    args=p.parse_args()
    files=sorted(Path(args.input).rglob("*"))
    files=[f for f in files if f.is_file()]
    if args.limit: files=files[:args.limit]
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for i,path in enumerate(files,1):
        try:
            radar=read_level2(path); fields=resolve_fields(radar)
            if fields["reflectivity"] is None: continue
            grid=grid_lowest_sweep(radar,fields["reflectivity"],grid_size_km=180.0,spacing_km=1.0)
            data=grid_field_2d(grid,fields["reflectivity"]); lat,lon=grid_latlon(grid)
            meta=volume_metadata(radar,path); ts=meta["scan_time_utc"]
            stamp=ts.strftime("%Y%m%dT%H%M%SZ")
            fig,ax=plt.subplots(figsize=(8,7),dpi=120)
            masked=np.ma.masked_invalid(data)
            ax.imshow(masked,origin="lower",extent=[float(np.nanmin(lon)),float(np.nanmax(lon)),float(np.nanmin(lat)),float(np.nanmax(lat))],
                      vmin=0,vmax=60,cmap="turbo",interpolation="nearest",alpha=0.82)
            ax.set_xlim(float(np.nanmin(lon)),float(np.nanmax(lon))); ax.set_ylim(float(np.nanmin(lat)),float(np.nanmax(lat)))
            ax.axis("off"); fig.subplots_adjust(0,0,1,1)
            name=f"{stamp}.png"; fig.savefig(out/name,transparent=True,pad_inches=0); plt.close(fig)
            manifest.append({"timestamp":ts.isoformat(),"file":f"frames/{name}"})
            print(f"[{i}/{len(files)}] {name}")
        except Exception as exc:
            print(f"SKIP {path}: {type(exc).__name__}: {exc}")
    (out/"frames.json").write_text(__import__("json").dumps(manifest,indent=2))
    print(f"Wrote {len(manifest)} radar frames to {out}")

if __name__=="__main__": main()
