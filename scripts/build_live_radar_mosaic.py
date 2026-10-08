"""Build KCXX/KTYX live reflectivity and base-velocity display products.

The display products are derived from the same downloaded Level-II volumes used
by object detection and feature generation. Reflectivity is mosaicked across
radars; signed radial velocity is kept as individual per-radar products because
radial velocity from different radar viewpoints should not be merged directly.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyart
import cmweather
from pyart.graph import cm as pyart_cm
from matplotlib.colors import BoundaryNorm, ListedColormap
from scipy import ndimage

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_available_sweep, grid_reflectivity_composite, lowest_valid_sweep
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

    # Display reflectivity uses a terrain-aware multi-sweep composite.
    # Object detection continues to use its own low-level radar fields.
    refl_grid = grid_reflectivity_composite(
        radar_obj,
        reflectivity,
        origin_lat=CENTER_LAT,
        origin_lon=CENTER_LON,
        grid_size_km=GRID_SIZE_KM,
        spacing_km=SPACING_KM,
        max_sweeps=6,
    )
    if refl_grid is None:
        raise RuntimeError(f"{radar}: reflectivity field has no valid sweep")

    data = grid_field_2d(refl_grid, reflectivity)
    # Treat each radar moment independently. A problem gridding velocity or
    # dual-pol must never discard an otherwise usable reflectivity volume.
    velocity_data = None
    velocity_field = fields.get("velocity")
    if velocity_field:
        try:
            velocity_grid = grid_lowest_available_sweep(
                radar_obj,
                velocity_field,
                origin_lat=CENTER_LAT,
                origin_lon=CENTER_LON,
                grid_size_km=GRID_SIZE_KM,
                spacing_km=SPACING_KM,
            )
            if velocity_grid is not None:
                velocity_data = grid_field_2d(velocity_grid, velocity_field)
        except Exception as exc:
            print(f"{radar}: base velocity gridding unavailable: {type(exc).__name__}: {exc}")
    rho = None
    if rhohv:
        try:
            rho_grid = grid_lowest_available_sweep(
                radar_obj,
                rhohv,
                origin_lat=CENTER_LAT,
                origin_lon=CENTER_LON,
                grid_size_km=GRID_SIZE_KM,
                spacing_km=SPACING_KM,
            )
            if rho_grid is not None:
                rho = grid_field_2d(rho_grid, rhohv)
        except Exception as exc:
            print(f"{radar}: rhoHV gridding unavailable: {type(exc).__name__}: {exc}")
    lat, lon = grid_latlon(refl_grid)
    return data, velocity_data, rho, lat, lon, meta.get("scan_time_utc"), meta.get("radar_id") or radar


def build_mosaic(raw_root: Path, states: dict[str, Path]):
    contributors = []
    fields = []
    rho_fields = []
    site_fields = {}
    site_velocity_fields = {}
    site_rho_fields = {}
    grid_lat = grid_lon = None

    for radar in RADARS:
        source = latest_source(raw_root, states[radar], radar)
        if source is None:
            continue
        try:
            data, velocity, rho, lat, lon, timestamp, radar_id = grid_radar(source, radar)
        except Exception as exc:
            print(f"{radar}: mosaic source unavailable: {type(exc).__name__}: {exc}")
            continue
        fields.append(data)
        rho_fields.append(rho)
        site_fields[radar] = data
        site_velocity_fields[radar] = velocity
        site_rho_fields[radar] = rho
        grid_lat, grid_lon = lat, lon
        contributors.append(
            {
                "radar": radar_id,
                "source_file": source.name,
                "scan_time_utc": timestamp,
            }
        )

    if not fields:
        return None, None, None, [], {}, {}, {}

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

    return mosaic, rho_mosaic, (grid_lat, grid_lon), contributors, site_fields, site_velocity_fields, site_rho_fields


def _clean_field(mosaic, rhohv=None):
    """QC the display field without blurring or averaging the radar data.

    The tracker/model never uses this display product.  Weak echoes are
    retained when they have local neighborhood support, while isolated
    low-level pixels and low-CC clutter are suppressed.  No Gaussian,
    median, or boxcar smoothing is applied.
    """
    data = np.asarray(mosaic, dtype=float).copy()

    # Keep weak echoes visible while removing only the lowest-level display noise.
    data[data < -10.0] = np.nan

    if rhohv is not None:
        # Conservative dual-pol clutter screen. It only removes low-CC echoes
        # below 30 dBZ, where non-meteorological returns are most common.
        low_cc = np.isfinite(rhohv) & (rhohv < 0.55) & (data < 25.0)
        data[low_cc] = np.nan

    # Edge-preserving neighborhood support filter. This removes isolated
    # speckles but does not change the value or blur the surviving pixels.
    present = np.isfinite(data)
    neighbors = ndimage.convolve(
        present.astype(np.uint8),
        np.ones((3, 3), dtype=np.uint8),
        mode="nearest",
    )
    isolated_weak = present & (neighbors <= 2) & (data < 12.0)
    data[isolated_weak] = np.nan

    return data


def _render(mosaic, latlon, output_path: Path, *, mode="clean", rhohv=None):
    lat, lon = latlon
    data = _clean_field(mosaic, rhohv) if mode == "clean" else np.asarray(mosaic, dtype=float)
    masked = np.ma.masked_invalid(data)

    fig = plt.figure(figsize=(12.0, 9.0), dpi=180)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
    ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))

    if mode == "clean":
        # Standard NWS radar reflectivity palette. Keep the clean display
        # identical to the raw/native reflectivity products so every frame
        # uses the familiar operational color scale.
        cmap = pyart_cm.NWSRef.copy()
        cmap.set_bad((0, 0, 0, 0))
        ax.pcolormesh(lon, lat, masked, cmap=cmap, vmin=-10, vmax=75, shading="auto")
    else:
        cmap = pyart_cm.NWSRef.copy()
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


def _render_velocity(velocity, latlon, output_path: Path, *, raw=False):
    lat, lon = latlon
    data = np.asarray(velocity, dtype=float) * 1.94384449244
    masked = np.ma.masked_invalid(data)

    if raw:
        cmap = plt.get_cmap("NWSVel").copy()
        cmap.set_bad((0, 0, 0, 0))
        limit = 80.0
        norm = None
    else:
        # Signed radial velocity palette. Green = inbound/toward, red =
        # outbound/away, with deliberately dense bins near 0–20 kt so subtle
        # low-level convergence/divergence is easier to interrogate.
        velocity_bounds = [-60, -40, -30, -20, -15, -10, -5, -2, 0, 2, 5, 10, 15, 20, 30, 40, 60]
        velocity_colors = [
            "#003b24", "#006b3c", "#15945a", "#55bd7a", "#8bd7a0",
            "#c4ebcf", "#e9f6ec", "#ffffff",
            "#fff0ef", "#f7c9c6", "#ef9993", "#e85f59", "#cf302c",
            "#a81822", "#7d1019", "#4f0710"
        ]
        cmap = ListedColormap(velocity_colors, name="BTV_WINTER_VELOCITY")
        cmap.set_bad((0, 0, 0, 0))
        limit = 60.0
        norm = BoundaryNorm(velocity_bounds, cmap.N)
    fig = plt.figure(figsize=(12.0, 9.0), dpi=180)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
    ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))
    if norm is None:
        ax.pcolormesh(lon, lat, masked, cmap=cmap, vmin=-limit, vmax=limit, shading="auto")
    else:
        ax.pcolormesh(lon, lat, masked, cmap=cmap, norm=norm, shading="auto")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="png", transparent=True, dpi=120, pad_inches=0)
    plt.close(fig)
    return [
        [float(np.nanmin(lat)), float(np.nanmin(lon))],
        [float(np.nanmax(lat)), float(np.nanmax(lon))],
    ]


def render_velocity(velocity, latlon, output_path: Path):
    return _render_velocity(velocity, latlon, output_path, raw=False)


def render_velocity_raw(velocity, latlon, output_path: Path):
    return _render_velocity(velocity, latlon, output_path, raw=True)


def render_site_products(
    site_fields,
    latlon,
    output_dir: Path,
    *,
    rhohv_by_site=None,
):
    """Render persistent individual KCXX/KTYX base-reflectivity products."""
    products = {}
    rhohv_by_site = rhohv_by_site or {}
    for site, field in site_fields.items():
        if field is None or not np.isfinite(field).any():
            continue
        clean_path = output_dir / f"{site}_base_reflectivity_clean.png"
        raw_path = output_dir / f"{site}_base_reflectivity_raw.png"
        bounds = render_clean(
            field,
            latlon,
            clean_path,
            rhohv=rhohv_by_site.get(site),
        )
        render_raw(field, latlon, raw_path)
        products[site] = {
            "clean_image": clean_path.name,
            "raw_image": raw_path.name,
            "bounds": bounds,
            "field": "base_reflectivity_dbz",
        }
    return products




def render_native_site_products(raw_root: Path, states: dict[str, Path], output_dir: Path):
    """Render true per-radar base reflectivity from the lowest valid Level-II sweep.

    These products intentionally bypass the Cartesian multi-sweep composite used
    by the model/mosaic path.  They are the browser's radar-like KCXX/KTYX
    displays and therefore correspond to the lowest valid native radar sweep.
    """
    products = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    for site in RADARS:
        source = latest_source(raw_root, states[site], site)
        if source is None:
            continue
        try:
            radar_obj = read_level2(source)
            fields = resolve_fields(radar_obj)
            refl = fields.get("reflectivity")
            if not refl:
                continue
            sweep = lowest_valid_sweep(radar_obj, refl)
            if sweep is None:
                continue
            data, lat, lon = _direct_sweep(radar_obj, refl, sweep)
            rho = None
            rho_name = fields.get("rhohv")
            if rho_name:
                try:
                    rho, _, _ = _direct_sweep(radar_obj, rho_name, sweep)
                except Exception as exc:
                    print(f"{site}: native rhoHV unavailable: {type(exc).__name__}: {exc}")

            item = {"data": data, "lat": lat, "lon": lon, "rho": rho}
            clean_name = f"{site}_base_reflectivity_clean.png"
            raw_name = f"{site}_base_reflectivity_raw.png"
            bounds, _ = _direct_render([item], output_dir, product_name=clean_name, clean=True)
            _direct_render([item], output_dir, product_name=raw_name, clean=False)
            meta = volume_metadata(radar_obj, source)
            products[site] = {
                "clean_image": clean_name,
                "raw_image": raw_name,
                "bounds": bounds,
                "field": "base_reflectivity_dbz",
                "source_file": source.name,
                "scan_time_utc": meta.get("scan_time_utc"),
                "sweep": int(sweep),
                "native_gates": True,
                "composite": False,
            }
        except Exception as exc:
            print(f"{site}: native base-reflectivity display unavailable: {type(exc).__name__}: {exc}")
    return products


def write_cursor_grid(output_dir: Path, mosaic, site_velocity_fields):
    """Publish compact 1-km cursor-sampling arrays for the browser viewer."""
    if mosaic is None:
        return None

    def encode(field, multiplier=1.0):
        arr = np.asarray(field, dtype=float)
        scaled = np.rint(arr * multiplier)
        return np.where(np.isfinite(scaled), scaled, -9999).astype(np.int16).reshape(-1).tolist()

    cursor = {
        "version": 1,
        "product": "BTV live radar cursor grid",
        "center_lat": CENTER_LAT,
        "center_lon": CENTER_LON,
        "spacing_km": SPACING_KM,
        "half_width_km": GRID_SIZE_KM,
        "shape": [int(mosaic.shape[0]), int(mosaic.shape[1])],
        "reflectivity_scale": 1,
        "reflectivity_missing": -9999,
        "reflectivity_dbz": encode(mosaic),
        "velocity_scale": 1,
        "velocity_missing": -9999,
        "velocity_units": "kt",
        "velocity_by_site": {},
    }
    for site in RADARS:
        field = site_velocity_fields.get(site)
        if field is None or not np.isfinite(field).any():
            continue
        cursor["velocity_by_site"][site] = encode(field, 1.94384449244)

    path = output_dir / "radar_cursor.json"
    path.write_text(json.dumps(cursor, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def _direct_sweep(radar_obj, field_name: str, sweep: int):
    """Return gate field and geographic coordinates without Cartesian gridding."""
    sw = radar_obj.extract_sweeps([sweep])
    data = sw.fields[field_name]["data"]
    lat = np.asarray(sw.gate_latitude["data"], dtype=float)
    lon = np.asarray(sw.gate_longitude["data"], dtype=float)
    if np.ma.isMaskedArray(data):
        data = data.filled(np.nan)
    else:
        data = np.asarray(data, dtype=float)
    return data, lat, lon


def _direct_render(sweep_products, output_dir: Path, *, product_name: str, clean: bool):
    """Render native lowest-sweep gates directly in geographic coordinates."""
    if not sweep_products:
        return None, {}
    fig = plt.figure(figsize=(12.0, 9.0), dpi=180)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(-76.78, -70.52)
    ax.set_ylim(41.90, 46.40)
    if clean:
        # Native Level-II reflectivity uses the same standard NWS palette as
        # the Cartesian mosaic and raw product.
        cmap = pyart_cm.NWSRef.copy()
        cmap.set_bad((0, 0, 0, 0))
        norm = None
    else:
        cmap = pyart_cm.NWSRef.copy()
        cmap.set_bad((0, 0, 0, 0))
        norm = None
    for item in sweep_products:
        data = np.asarray(item["data"], dtype=float).copy()
        if clean:
            data[data < -10.0] = np.nan
            rho = item.get("rho")
            if rho is not None:
                low_cc = np.isfinite(rho) & (rho < 0.65) & (data < 30.0)
                data[low_cc] = np.nan
            present = np.isfinite(data)
            neighbors = ndimage.convolve(
                present.astype(np.uint8),
                np.ones((3, 3), dtype=np.uint8),
                mode="nearest",
            )
            data[present & (neighbors <= 2) & (data < 12.0)] = np.nan
        masked = np.ma.masked_invalid(data)
        if masked.count():
            kwargs = {"cmap": cmap, "shading": "auto"}
            if norm is None:
                kwargs.update(vmin=-10, vmax=75)
            else:
                kwargs["norm"] = norm
            ax.pcolormesh(item["lon"], item["lat"], masked, **kwargs)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / product_name
    fig.savefig(path, format="png", transparent=True, dpi=180, pad_inches=0)
    plt.close(fig)
    return [[41.90, -76.78], [46.40, -70.52]], path.name


def _direct_velocity_render(item, output_dir: Path, site: str):
    data = np.asarray(item["velocity"], dtype=float) * 1.94384449244
    masked = np.ma.masked_invalid(data)
    if not masked.count():
        return None
    fig = plt.figure(figsize=(12.0, 9.0), dpi=180)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(-76.78, -70.52)
    ax.set_ylim(41.90, 46.40)
    velocity_bounds = [-60, -40, -30, -20, -15, -10, -5, -2, 0, 2, 5, 10, 15, 20, 30, 40, 60]
    velocity_colors = [
        "#003b24", "#006b3c", "#15945a", "#55bd7a", "#8bd7a0",
        "#c4ebcf", "#e9f6ec", "#ffffff",
        "#fff0ef", "#f7c9c6", "#ef9993", "#e85f59", "#cf302c",
        "#a81822", "#7d1019", "#4f0710"
    ]
    cmap = ListedColormap(velocity_colors, name="BTV_WINTER_VELOCITY")
    cmap.set_bad((0, 0, 0, 0))
    norm = BoundaryNorm(velocity_bounds, cmap.N)
    ax.pcolormesh(item["lon"], item["lat"], masked, cmap=cmap, norm=norm, shading="auto")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{site}_base_velocity_clean.png"
    fig.savefig(path, format="png", transparent=True, dpi=120, pad_inches=0)
    plt.close(fig)
    raw_path = output_dir / f"{site}_base_velocity_raw.png"
    import shutil
    shutil.copyfile(path, raw_path)
    return {"clean_image":path.name,"raw_image":raw_path.name,"bounds":[[41.90,-76.78],[46.40,-70.52]],"field":"base_velocity_kt","native_units":"m/s","display_units":"kt"}


def build_direct_fallback(raw_root: Path, states: dict[str, Path]):
    """Build browser products directly from native Level-II gates."""
    products=[]; sources=[]
    for radar in RADARS:
        source=latest_source(raw_root,states[radar],radar)
        if source is None: continue
        try:
            radar_obj=read_level2(source)
            fields=resolve_fields(radar_obj); refl=fields.get("reflectivity")
            if not refl: continue
            sweep=lowest_valid_sweep(radar_obj,refl)
            if sweep is None: continue
            data,lat,lon=_direct_sweep(radar_obj,refl,sweep)
            rho=None
            if fields.get("rhohv"):
                try: rho,_,_=_direct_sweep(radar_obj,fields["rhohv"],sweep)
                except Exception: rho=None
            velocity=None
            if fields.get("velocity"):
                try: velocity,_,_=_direct_sweep(radar_obj,fields["velocity"],sweep)
                except Exception as exc: print(f"{radar}: direct velocity unavailable: {type(exc).__name__}: {exc}")
            products.append({"radar":radar,"data":data,"lat":lat,"lon":lon,"rho":rho,"velocity":velocity})
            meta=volume_metadata(radar_obj,source)
            sources.append({"radar":meta.get("radar_id") or radar,"source_file":source.name,"scan_time_utc":meta.get("scan_time_utc")})
        except Exception as exc:
            print(f"{radar}: direct display fallback failed: {type(exc).__name__}: {exc}")
    if not products: return None
    output_dir=raw_root.parent/"viewer"/"data"/"live"
    bounds,_=_direct_render(products,output_dir,product_name="radar_mosaic_native_clean.png",clean=True)
    _direct_render(products,output_dir,product_name="radar_mosaic_native_raw.png",clean=False)
    velocity_products={}
    for item in products:
        if item.get("velocity") is None: continue
        vp=_direct_velocity_render(item,output_dir,item["radar"])
        if vp: velocity_products[item["radar"]]=vp
    return {"bounds":bounds,"sources":sources,"velocity_products":velocity_products}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--kcxx-state", type=Path, required=True)
    parser.add_argument("--ktyx-state", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    states = {"KCXX": args.kcxx_state, "KTYX": args.ktyx_state}
    mosaic, rhohv, latlon, contributors, site_fields, site_velocity_fields, site_rho_fields = build_mosaic(args.raw_root, states)
    direct_fallback = build_direct_fallback(args.raw_root, states)

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
            "color_table": "NWSRef",
            "vmin_dbz": -10,
            "vmax_dbz": 75,
            "display_qc": {
                "low_dbz_cutoff": -10,
                "low_cc_threshold": 0.65,
                "low_cc_max_dbz": 30,
                "isolated_weak_echo_cleanup": True,
                "cleanup_method": "3x3 neighborhood support; no smoothing",
            },
        },
        "display_products": {
            "default": "clean",
            "clean_image": "radar_mosaic_clean.png",
            "raw_image": "radar_mosaic_raw.png",
            "base_reflectivity": {
                "KCXX": {
                    "clean_image": "KCXX_base_reflectivity_clean.png",
                    "raw_image": "KCXX_base_reflectivity_raw.png",
                },
                "KTYX": {
                    "clean_image": "KTYX_base_reflectivity_clean.png",
                    "raw_image": "KTYX_base_reflectivity_raw.png",
                },
            },
            "clean_description": "Standard NWSRef reflectivity palette with edge-preserving neighborhood QC. No smoothing; does not alter model input.",
            "raw_description": "Unfiltered gridded KCXX/KTYX reflectivity mosaic.",
            "base_reflectivity_description": "Native-gate lowest-valid-sweep base reflectivity from the downloaded KCXX and KTYX Level-II volumes; not a multi-sweep composite.",
        },
        "sources": contributors,
        "image": "radar_mosaic_clean.png" if mosaic is not None else None,
    }

    if mosaic is not None:
        # One canonical browser reflectivity path: the Cartesian KCXX/KTYX
        # mosaic rendered once with the standard NWSRef palette. Native-gate
        # products remain available as separate per-radar diagnostics, but do
        # not replace or mutate the browser-facing mosaic image.
        clean_output = args.output_image.parent / "radar_mosaic_clean.png"
        raw_output = args.output_image.parent / "radar_mosaic_raw.png"
        bounds = render_clean(mosaic, latlon, clean_output, rhohv=rhohv)
        render_raw(mosaic, latlon, raw_output)
        # radar_mosaic.png is a compatibility alias and must contain the exact
        # same pixels as the canonical clean product.
        shutil.copyfile(clean_output, args.output_image)
        payload["bounds"] = bounds
        # Individual radar displays must be true base reflectivity: the
        # lowest valid native Level-II sweep. Do not expose the multi-sweep
        # Cartesian composite here; that product remains available only to the
        # mosaic/model path.
        site_products = render_native_site_products(
            args.raw_root,
            states,
            args.output_image.parent,
        )
        payload["display_products"]["base_reflectivity"] = site_products
        velocity_products = {}
        for site, velocity in site_velocity_fields.items():
            if velocity is None or not np.isfinite(velocity).any():
                continue
            clean_path = args.output_image.parent / f"{site}_base_velocity_clean.png"
            raw_path = args.output_image.parent / f"{site}_base_velocity_raw.png"
            vbounds = render_velocity(velocity, latlon, clean_path)
            render_velocity_raw(velocity, latlon, raw_path)
            velocity_products[site] = {
                "clean_image": clean_path.name,
                "raw_image": raw_path.name,
                "bounds": vbounds,
                "field": "base_velocity_kt",
                "native_units": "m/s",
                "display_units": "kt",
            }
        # If Cartesian velocity gridding failed for a site, recover that site from native Level-II gates.
        if direct_fallback is not None:
            velocity_products.update({k:v for k,v in direct_fallback["velocity_products"].items() if k not in velocity_products})
        payload["display_products"]["base_velocity"] = velocity_products
        payload["radar_moment_products"] = {
            "velocity_native_units": "m/s",
            "velocity_display_units": "kt",
            "velocity_rendering": "signed_radial_velocity",
            "velocity_sources": sorted(velocity_products),
        }
        cursor_path = write_cursor_grid(args.output_image.parent, mosaic, site_velocity_fields)
        payload["cursor_grid"] = {
            "file": cursor_path.name if cursor_path is not None else None,
            "spacing_km": SPACING_KM,
            "shape": [int(mosaic.shape[0]), int(mosaic.shape[1])],
            "velocity_sources": sorted(velocity_products),
            "status": "ready" if cursor_path is not None else "unavailable",
        }
    else:
        if direct_fallback is not None:
            payload["status"]="ready"
            payload["stale_reason"]="Native-gate display fallback used because Cartesian radar gridding was unavailable."
            payload["bounds"]=direct_fallback["bounds"]
            payload["sources"]=direct_fallback["sources"]
            payload["image"]="radar_mosaic_clean.png"
            payload["display_products"]["base_velocity"]=direct_fallback["velocity_products"]
            payload["radar_moment_products"]={"velocity_native_units":"m/s","velocity_display_units":"kt","velocity_rendering":"signed_radial_velocity","velocity_sources":sorted(direct_fallback["velocity_products"])}
        # Never destroy the last good radar display just because one publisher
        # cycle cannot acquire a usable Level-II volume. The live workflow
        # restores the previous viewer payload before rebuilding this product.
        # Preserve those images and mark the metadata stale instead.
        previous = {}
        try:
            if args.output_json.exists():
                previous = json.loads(args.output_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        previous_sources = previous.get("sources") or []
        previous_bounds = previous.get("bounds")
        previous_products = previous.get("display_products") or {}
        if previous_sources and previous_bounds:
            payload["status"] = "stale"
            payload["stale_reason"] = "No new usable KCXX/KTYX Level-II volume was available; retaining last successful radar display."
            payload["bounds"] = previous_bounds
            payload["sources"] = previous_sources
            payload["display_products"] = previous_products
            payload["image"] = previous.get("image") or "radar_mosaic_clean.png"
            if previous.get("radar_moment_products") is not None:
                payload["radar_moment_products"] = previous["radar_moment_products"]
            if previous.get("cursor_grid") is not None:
                payload["cursor_grid"] = previous["cursor_grid"]

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
