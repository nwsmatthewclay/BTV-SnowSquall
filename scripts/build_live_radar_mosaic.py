"""Build a small, georeferenced KCXX/KTYX real-time reflectivity mosaic for the live viewer.

The mosaic is a display product only. The live model continues to consume decoded
Level-II data and radar-derived predictors directly. The viewer receives two
renderings:
  * radar_mosaic_clean.png - clutter-suppressed human display (default)
  * radar_mosaic_raw.png   - unfiltered scientific display
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
import cmweather
from matplotlib.colors import BoundaryNorm, ListedColormap
from scipy import ndimage

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
    if not radar_dir.exists():
        return None
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
    rhohv = fields.get("rhohv")

    requested = [reflectivity] + ([rhohv] if rhohv else [])
    grid = grid_lowest_sweep(
        radar_obj,
        requested,
        origin_lat=CENTER_LAT,
        origin_lon=CENTER_LON,
        grid_size_km=GRID_SIZE_KM,
        spacing_km=SPACING_KM,
    )

    data = grid_field_2d(grid, reflectivity)
    rho = grid_field_2d(grid, rhohv) if rhohv and rhohv in getattr(grid, "fields", {}) else None
    lat, lon = grid_latlon(grid)
    return data, rho, lat, lon, meta.get("scan_time_utc"), meta.get("radar_id") or radar


def build_mosaic(raw_root: Path, states: dict[str, Path]):
    contributors = []
    fields = []
    rho_fields = []
    grid_lat = grid_lon = None

    for radar in RADARS:
        source = latest_source(raw_root, states[radar], radar)
        if source is None:
            continue
        try:
            data, rho, lat, lon, timestamp, radar_id = grid_radar(source, radar)
        except Exception as exc:
            print(f"{radar}: mosaic source unavailable: {type(exc).__name__}: {exc}")
            continue
        fields.append(data)
        rho_fields.append(rho)
        grid_lat, grid_lon = lat, lon
        contributors.append(
            {
                "radar": radar_id,
                "source_file": source.name,
                "scan_time_utc": timestamp,
            }
        )

    if not fields:
        return None, None, None, []

    mosaic = np.full_like(fields[0], np.nan, dtype=float)
    for field in fields:
        valid = np.isfinite(field)
        if not np.any(valid):
            continue
        new_only = valid & ~np.isfinite(mosaic)
        overlap = valid & np.isfinite(mosaic)
        mosaic[new_only] = field[new_only]
        mosaic[overlap] = np.maximum(mosaic[overlap], field[overlap])

    rho_mosaic = None
    if any(r is not None for r in rho_fields):
        rho_mosaic = np.full_like(mosaic, np.nan, dtype=float)
        for rho in rho_fields:
            if rho is None:
                continue
            valid = np.isfinite(rho)
            new_only = valid & ~np.isfinite(rho_mosaic)
            overlap = valid & np.isfinite(rho_mosaic)
            rho_mosaic[new_only] = rho[new_only]
            rho_mosaic[overlap] = np.maximum(rho_mosaic[overlap], rho[overlap])

    return mosaic, rho_mosaic, (grid_lat, grid_lon), contributors


def _clean_field(mosaic, rhohv=None):
    data = np.asarray(mosaic, dtype=float).copy()

    # Keep weak snow visible but remove the lowest-level display noise.
    data[data < 12.0] = np.nan

    if rhohv is not None:
        # Conservative dual-pol clutter screen. It only removes low-CC echoes
        # below 30 dBZ, where non-meteorological returns are most common.
        low_cc = np.isfinite(rhohv) & (rhohv < 0.65) & (data < 30.0)
        data[low_cc] = np.nan

    # Remove isolated weak speckles while preserving coherent bands.
    present = np.isfinite(data)
    cleaned = ndimage.binary_opening(present, structure=np.ones((2, 2)))
    data[present & ~cleaned & (data < 24.0)] = np.nan

    return data


def _render(mosaic, latlon, output_path: Path, *, mode="clean", rhohv=None):
    lat, lon = latlon
    data = _clean_field(mosaic, rhohv) if mode == "clean" else np.asarray(mosaic, dtype=float)
    masked = np.ma.masked_invalid(data)

    fig = plt.figure(figsize=(8.5, 6.5), dpi=120)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
    ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))

    if mode == "clean":
        bounds = [12, 18, 24, 30, 35, 40, 45, 55, 65, 75]
        colors = [
            (0.18, 0.28, 0.36, 0.12),  # weak echo
            (0.25, 0.45, 0.58, 0.25),
            (0.25, 0.65, 0.86, 0.42),
            (0.10, 0.72, 0.50, 0.58),
            (0.52, 0.82, 0.24, 0.72),
            (0.95, 0.84, 0.18, 0.82),
            (0.96, 0.55, 0.10, 0.90),
            (0.86, 0.18, 0.12, 0.96),
            (0.92, 0.25, 0.72, 1.0),
        ]
        cmap = ListedColormap(colors, name="BTV_SNOWSQUALL_CLEAN")
        norm = BoundaryNorm(bounds, cmap.N)
        ax.pcolormesh(lon, lat, masked, cmap=cmap, norm=norm, shading="auto")
    else:
        cmap = plt.get_cmap("NWSRef").copy()
        cmap.set_bad((0, 0, 0, 0))
        ax.pcolormesh(lon, lat, masked, cmap=cmap, vmin=-10, vmax=75, shading="auto")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="png", transparent=True, dpi=120, pad_inches=0)
    plt.close(fig)

    return [
        [float(np.nanmin(lat)), float(np.nanmin(lon))],
        [float(np.nanmax(lat)), float(np.nanmax(lon))],
    ]


def render_clean(mosaic, latlon, output_path: Path, rhohv=None):
    return _render(mosaic, latlon, output_path, mode="clean", rhohv=rhohv)


def render_raw(mosaic, latlon, output_path: Path):
    return _render(mosaic, latlon, output_path, mode="raw")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--kcxx-state", type=Path, required=True)
    parser.add_argument("--ktyx-state", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    states = {"KCXX": args.kcxx_state, "KTYX": args.ktyx_state}
    mosaic, rhohv, latlon, contributors = build_mosaic(args.raw_root, states)

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
            "color_table": "BTV_SNOWSQUALL_CLEAN + NWSRef_RAW",
            "vmin_dbz": 12,
            "vmax_dbz": 75,
            "display_qc": {
                "low_dbz_cutoff": 12,
                "low_cc_threshold": 0.65,
                "low_cc_max_dbz": 30,
                "isolated_weak_echo_cleanup": True,
            },
        },
        "display_products": {
            "default": "clean",
            "clean_image": "radar_mosaic_clean.png",
            "raw_image": "radar_mosaic_raw.png",
            "clean_description": "Clutter-suppressed human display. This does not alter model input.",
            "raw_description": "Unfiltered gridded reflectivity display.",
        },
        "sources": contributors,
        "image": "radar_mosaic_clean.png" if mosaic is not None else None,
    }

    if mosaic is not None:
        bounds = render_clean(mosaic, latlon, args.output_image, rhohv=rhohv)
        clean_output = args.output_image.with_name("radar_mosaic_clean.png")
        raw_output = args.output_image.with_name("radar_mosaic_raw.png")
        render_clean(mosaic, latlon, clean_output, rhohv=rhohv)
        render_raw(mosaic, latlon, raw_output)
        if args.output_image.name != "radar_mosaic_clean.png":
            args.output_image.unlink(missing_ok=True)
            # Preserve the existing viewer contract name as the clean product.
            clean_output.replace(args.output_image)
            # Re-create the clean product at its explicit canonical name.
            render_clean(mosaic, latlon, clean_output, rhohv=rhohv)
        payload["bounds"] = bounds
    else:
        for output in (
            args.output_image,
            args.output_image.with_name("radar_mosaic_clean.png"),
            args.output_image.with_name("radar_mosaic_raw.png"),
        ):
            output.unlink(missing_ok=True)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
