"""Build a small, georeferenced KCXX/KTYX real-time reflectivity mosaic for the live viewer.

The mosaic is a display product only. The live model continues to consume decoded
Level-II data and radar-derived predictors directly. When both radars are
available, overlapping grid cells use the maximum valid reflectivity.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyart
import cmweather  # Registers Py-ART/cmweather field-specific colormaps.

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep
from processing.radar_sites import apply_radar_origin, radar_origin_for_site


CENTER_LAT = 44.15
CENTER_LON = -73.65
GRID_SIZE_KM = 250.0
SPACING_KM = 1.0
RADARS = ("KCXX", "KTYX")


def read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def latest_source(raw_root: Path, state_path: Path, radar: str) -> Path | None:
    state = read_state(state_path)
    source = state.get("last_source")
    if source:
        candidate = raw_root / radar / Path(str(source)).name
        if candidate.exists() and candidate.stat().st_size:
            return candidate
    radar_dir = raw_root / radar
    candidates = sorted(
        (p for p in radar_dir.glob("*") if p.is_file() and p.stat().st_size),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def grid_radar(path: Path, radar: str):
    radar_obj = read_level2(path)
    meta = volume_metadata(radar_obj, path)
    apply_radar_origin(radar_obj, radar_origin_for_site(radar))

    fields = resolve_fields(radar_obj)
    reflectivity = fields.get("reflectivity")
    if not reflectivity:
        raise RuntimeError(f"{radar}: no reflectivity field found")

    grid = grid_lowest_sweep(
        radar_obj,
        [reflectivity],
        origin_lat=CENTER_LAT,
        origin_lon=CENTER_LON,
        grid_size_km=GRID_SIZE_KM,
        spacing_km=SPACING_KM,
    )
    data = grid_field_2d(grid, reflectivity)
    lat, lon = grid_latlon(grid)
    return data, lat, lon, meta.get("scan_time_utc"), meta.get("radar_id") or radar


def build_mosaic(raw_root: Path, states: dict[str, Path]):
    contributors = []
    fields = []
    grid_lat = grid_lon = None

    for radar in RADARS:
        source = latest_source(raw_root, states[radar], radar)
        if source is None:
            continue
        try:
            data, lat, lon, timestamp, radar_id = grid_radar(source, radar)
        except Exception as exc:
            print(f"{radar}: mosaic source unavailable: {type(exc).__name__}: {exc}")
            continue
        fields.append(data)
        grid_lat, grid_lon = lat, lon
        contributors.append(
            {
                "radar": radar_id,
                "source_file": source.name,
                "scan_time_utc": timestamp,
            }
        )

    if not fields:
        return None, None, []

    mosaic = np.full_like(fields[0], np.nan, dtype=float)
    for field in fields:
        valid = np.isfinite(field)
        if not np.any(valid):
            continue
        both = valid & np.isfinite(mosaic)
        mosaic[valid & ~np.isfinite(mosaic)] = field[valid & ~np.isfinite(mosaic)]
        mosaic[both] = np.maximum(mosaic[both], field[both])

    return mosaic, (grid_lat, grid_lon), contributors


def render(mosaic, latlon, output_path: Path):
    lat, lon = latlon
    masked = np.ma.masked_invalid(mosaic)

    fig = plt.figure(figsize=(8.5, 6.5), dpi=120)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
    ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))

    cmap = plt.get_cmap("NWSRef").copy()
    cmap.set_bad((0, 0, 0, 0))
    ax.pcolormesh(
        lon,
        lat,
        masked,
        cmap=cmap,
        vmin=-10,
        vmax=75,
        shading="auto",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_path,
        format="png",
        transparent=True,
        dpi=120,
        pad_inches=0,
    )
    plt.close(fig)

    bounds = [
        [float(np.nanmin(lat)), float(np.nanmin(lon))],
        [float(np.nanmax(lat)), float(np.nanmax(lon))],
    ]
    return bounds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--kcxx-state", type=Path, required=True)
    parser.add_argument("--ktyx-state", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    states = {"KCXX": args.kcxx_state, "KTYX": args.ktyx_state}
    mosaic, latlon, contributors = build_mosaic(args.raw_root, states)

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "product": "BTV live radar mosaic",
        "status": "ready" if mosaic is not None else "unavailable",
        "updated_utc": now,
        "grid": {
            "center_lat": CENTER_LAT,
            "center_lon": CENTER_LON,
            "grid_size_km": GRID_SIZE_KM,
            "spacing_km": SPACING_KM,
            "combine_method": "maximum valid reflectivity",
            "field": "reflectivity_dbz",
            "color_table": "Py-ART NWSRef",
            "vmin_dbz": -10,
            "vmax_dbz": 75,
        },
        "sources": contributors,
        "image": "radar_mosaic.png" if mosaic is not None else None,
    }

    if mosaic is not None:
        payload["bounds"] = render(mosaic, latlon, args.output_image)
    else:
        args.output_image.unlink(missing_ok=True)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
