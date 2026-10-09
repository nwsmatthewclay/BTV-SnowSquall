#!/usr/bin/env python3
"""Acquire and publish a fresh KCXX/KTYX radar mosaic independently of object processing.

This path exists so a slow or failing object/model job cannot leave the operational
radar display pinned to an old scan.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from acquisition.radar_watcher import (
    download_volume,
    find_newest_volume,
    make_s3_client,
)
from scripts.build_live_radar_mosaic import build_mosaic


RADARS = ("KCXX", "KTYX")
DEFAULT_MAX_AGE_MINUTES = 20.0


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-root", type=Path, default=Path("viewer/data/live"))
    parser.add_argument("--max-age-minutes", type=float, default=DEFAULT_MAX_AGE_MINUTES)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    args.raw_root.mkdir(parents=True, exist_ok=True)

    s3 = make_s3_client()
    selected: dict[str, tuple[str, datetime]] = {}

    for radar in RADARS:
        newest = find_newest_volume(s3, radar)
        if newest is None:
            print(f"{radar}: no recent Level-II volume found")
            continue

        key, volume_time = newest
        path = download_volume(s3, radar, key, volume_time)
        selected[radar] = (path.name, volume_time)
        age = (datetime.now(timezone.utc) - volume_time).total_seconds() / 60.0
        print(f"{radar}: {path.name} scan={volume_time.isoformat()} age={age:.1f} min")

    if not selected:
        raise SystemExit("No KCXX/KTYX Level-II volumes were available.")

    # Point the mosaic builder at the exact volumes selected above. Empty
    # state files make latest_source() fall back to the newest file in raw/.
    with tempfile.TemporaryDirectory(prefix="btv-live-radar-") as tmp:
        tmp_path = Path(tmp)
        state_paths: dict[str, Path] = {}
        for radar, (filename, _) in selected.items():
            state_path = tmp_path / f"{radar}_state.json"
            state_path.write_text(
                json.dumps({"last_source": filename}) + "\n",
                encoding="utf-8",
            )
            state_paths[radar] = state_path

        # The builder expects both state keys, even when one radar is temporarily
        # unavailable. An empty state lets that radar be skipped cleanly.
        for radar in RADARS:
            state_paths.setdefault(radar, tmp_path / f"{radar}_state.json")
            if not state_paths[radar].exists():
                state_paths[radar].write_text("{}\n", encoding="utf-8")

        output_image = args.output_root / "radar_mosaic.png"
        output_json = args.output_root / "radar_mosaic.json"

        mosaic, rhohv, latlon, contributors, site_fields, site_velocity_fields, site_rho_fields = build_mosaic(
            args.raw_root,
            state_paths,
        )
        if mosaic is None or not contributors:
            raise SystemExit("Radar mosaic builder produced no usable radar data.")

        # Reuse the canonical renderer path from the existing builder.
        from scripts import build_live_radar_mosaic as renderer

        renderer.render_clean(
            mosaic,
            latlon,
            args.output_root / "radar_mosaic_clean.png",
            rhohv=rhohv,
            site_fields=site_fields,
            rhohv_by_site=site_rho_fields,
        )
        renderer.render_raw(
            mosaic,
            latlon,
            args.output_root / "radar_mosaic_raw.png",
        )

        site_products = renderer.render_site_products(
            site_fields,
            latlon,
            args.output_root,
            rhohv_by_site=site_rho_fields,
        )

        velocity_products = {}
        for site, velocity in site_velocity_fields.items():
            if velocity is None:
                continue
            import numpy as np
            if not np.isfinite(velocity).any():
                continue
            clean = args.output_root / f"{site}_base_velocity_clean.png"
            raw = args.output_root / f"{site}_base_velocity_raw.png"
            bounds = renderer.render_velocity(velocity, latlon, clean)
            renderer.render_velocity_raw(velocity, latlon, raw)
            velocity_products[site] = {
                "clean_image": clean.name,
                "raw_image": raw.name,
                "bounds": bounds,
                "field": "base_velocity_kt",
                "native_units": "m/s",
                "display_units": "kt",
            }

        now = datetime.now(timezone.utc)
        scan_times = [
            parse_timestamp(item.get("scan_time_utc"))
            for item in contributors
        ]
        scan_times = [t for t in scan_times if t is not None]
        newest_scan = max(scan_times)

        cursor_path = renderer.write_cursor_grid(
            args.output_root,
            mosaic,
            site_velocity_fields,
        )

        payload = {
            "product": "BTV live radar mosaic",
            "status": "ready",
            "updated_utc": now.isoformat(),
            "grid": {
                "center_lat": renderer.CENTER_LAT,
                "center_lon": renderer.CENTER_LON,
                "grid_size_km": renderer.GRID_SIZE_KM,
                "spacing_km": renderer.SPACING_KM,
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
                "base_reflectivity": site_products,
                "base_velocity": velocity_products,
                "clean_description": "Standard NWSRef reflectivity palette with edge-preserving neighborhood QC. No smoothing; does not alter model input.",
                "raw_description": "Unfiltered gridded KCXX/KTYX reflectivity mosaic.",
                "base_reflectivity_description": "Individual lowest-valid-sweep base-reflectivity displays.",
            },
            "sources": contributors,
            "image": "radar_mosaic_clean.png",
            "bounds": [
                [float(latlon[0].min()), float(latlon[1].min())],
                [float(latlon[0].max()), float(latlon[1].max())],
            ],
            "radar_moment_products": {
                "velocity_native_units": "m/s",
                "velocity_display_units": "kt",
                "velocity_rendering": "signed_radial_velocity",
                "velocity_sources": sorted(velocity_products),
            },
            "cursor_grid": {
                "file": cursor_path.name if cursor_path is not None else None,
                "spacing_km": renderer.SPACING_KM,
                "shape": [int(mosaic.shape[0]), int(mosaic.shape[1])],
                "velocity_sources": sorted(velocity_products),
                "status": "ready" if cursor_path is not None else "unavailable",
            },
        }

        age = (now - newest_scan).total_seconds() / 60.0
        print(f"Newest usable radar scan: {newest_scan.isoformat()} age={age:.1f} minutes")
        if age > args.max_age_minutes:
            raise SystemExit(
                f"Newest usable radar scan is stale: {age:.1f} minutes > {args.max_age_minutes:.1f}"
            )

        output_json.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        output_image.write_bytes((args.output_root / "radar_mosaic_clean.png").read_bytes())
        print("Radar-only build complete:", output_json)


if __name__ == "__main__":
    main()
