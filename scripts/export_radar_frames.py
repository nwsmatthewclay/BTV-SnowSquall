"""Render compact geographic radar frames for the static object viewer."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.radar_grid import grid_field_2d, grid_lowest_sweep, grid_latlon

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--limit",type=int,default=0); args=p.parse_args()
    files=[f for f in sorted(Path(args.input).rglob("*")) if f.is_file()]
    if args.limit: files=files[:args.limit]
    out=Path(args.output_dir); frames=out/"frames"; frames.mkdir(parents=True,exist_ok=True)
    manifest=[]; bounds=None
    for i,path in enumerate(files,1):
        try:
            radar=read_level2(path); field=resolve_fields(radar)["reflectivity"]
            if field is None: continue
            grid=grid_lowest_sweep(radar,field,grid_size_km=180.0,spacing_km=1.0); data=grid_field_2d(grid,field); lat,lon=grid_latlon(grid)
            west,east=float(np.nanmin(lon)),float(np.nanmax(lon)); south,north=float(np.nanmin(lat)),float(np.nanmax(lat))
            bounds=bounds or [[south,west],[north,east]]
            ts=volume_metadata(radar,path)["scan_time_utc"]; stamp=ts.strftime("%Y%m%dT%H%M%SZ")
            fig,ax=plt.subplots(figsize=(8,7),dpi=120); ax.imshow(np.ma.masked_invalid(data),origin="lower",extent=[west,east,south,north],vmin=0,vmax=60,cmap="turbo",interpolation="nearest",alpha=.82)
            ax.set_xlim(west,east); ax.set_ylim(south,north); ax.axis("off"); fig.subplots_adjust(0,0,1,1); fig.savefig(frames/f"{stamp}.png",transparent=True,pad_inches=0); plt.close(fig)
            manifest.append({"timestamp":ts.isoformat(),"file":f"frames/{stamp}.png"})
            print(f"[{i}/{len(files)}] {stamp}")
        except Exception as exc: print(f"SKIP {path}: {type(exc).__name__}: {exc}")
    (out/"frames.json").write_text(json.dumps({"bounds":bounds,"frames":manifest},indent=2))
    print(f"Wrote {len(manifest)} radar frames to {out}")

if __name__=="__main__": main()
