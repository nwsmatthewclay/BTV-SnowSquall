"""Persist one row per tracked radar object per scan.

The history store is append-only and leakage-safe: each record contains only
information available at that object's observation time. Future outcome/label
columns are intentionally left null until a separate labeling pass populates
them.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

CSV_FIELDS = [
    "timestamp", "radar_site", "source_file", "track_id",
    "centroid_lat", "centroid_lon", "pixel_count", "area_km2",
    "length_km", "width_km", "aspect_ratio", "orientation_deg",
    "max_reflectivity_dbz", "mean_reflectivity_dbz", "core_pixel_count",
    "core_fraction", "motion_speed_kt", "motion_dir_deg",
    "age_scans", "reflectivity_trend_dbz_per_hr", "area_growth_fraction",
    "environment_status", "environment_source", "environment_valid_time_utc",
    "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient", "vertical_valid_points",
    "zdr_mean_db", "zdr_p90_db", "zdr_gradient_dbkm", "rhohv_mean", "rhohv_max", "rhohv_p90", "rhohv_min",
    "kdp_mean_degkm", "kdp_p90_degkm", "velocity_mean_kt", "velocity_std_kt", "velocity_p90_abs_kt", "velocity_gradient_ktkm",
    "environment_age_minutes",
    "snsq", "mean_rh_0_2km_pct", "thetae_delta_0_2km_k", "mean_wind_0_2km_ms", "wetbulb_2m_c",
    "snsq_moisture_factor", "snsq_instability_factor", "snsq_wind_factor", "snsq_snow_temperature_pass",
    "visibility_m", "gust_ms", "surface_temperature_k",
    "cape_jkg", "cin_jkg", "pwat_mm", "mlcape_jkg", "mlcin_jkg",
    "mucape_jkg", "mucin_jkg", "srh01_m2s2", "srh03_m2s2",
    "shear_u_0_6km_ms", "shear_v_0_6km_ms", "shear_0_6km_ms",
    "u10_ms", "v10_ms", "temperature_2m_k", "dewpoint_2m_k",
    "rh_2m_pct", "data_quality", "model_version",
    "label_status", "snow_squall_outcome",
]


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    return value


def flatten(feature, source_file):
    props = feature.get("properties", {})
    env = props.get("environment") or {}
    fields = env.get("fields") or {}
    row = {key: None for key in CSV_FIELDS}

    direct = [
        "timestamp", "radar_site", "track_id", "centroid_lat", "centroid_lon",
        "pixel_count", "area_km2", "length_km", "width_km", "aspect_ratio",
        "orientation_deg", "max_reflectivity_dbz", "mean_reflectivity_dbz",
        "core_pixel_count", "core_fraction", "motion_speed_kt",
        "motion_dir_deg", "age_scans", "reflectivity_trend_dbz_per_hr",
        "area_growth_fraction", "environment_status", "data_quality",
        "model_version",
        "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient", "vertical_valid_points",
        "zdr_mean_db", "zdr_p90_db", "zdr_gradient_dbkm", "rhohv_mean", "rhohv_max", "rhohv_p90", "rhohv_min",
        "kdp_mean_degkm", "kdp_p90_degkm", "velocity_mean_kt", "velocity_std_kt", "velocity_p90_abs_kt", "velocity_gradient_ktkm",
    ]
    for key in direct:
        row[key] = _clean(props.get(key))

    row["source_file"] = source_file
    row["environment_source"] = env.get("source")
    row["environment_valid_time_utc"] = env.get("source_valid_time_utc")
    row["environment_age_minutes"] = _clean(env.get("age_minutes"))

    for key in CSV_FIELDS:
        if key in fields:
            row[key] = _clean(fields[key])

    # Labels are deliberately empty until a separate historical labeling pass.
    row["label_status"] = "unlabeled"
    row["snow_squall_outcome"] = None
    return row


def append_history(geojson_path: Path, jsonl_path: Path, csv_path: Path):
    payload = json.loads(geojson_path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    source_file = metadata.get("source_file")

    rows = [
        flatten(feature, source_file)
        for feature in payload.get("features", [])
    ]
    if not rows:
        return 0

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    existing_keys = set()
    if jsonl_path.exists():
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    existing_keys.add(
                        (item.get("timestamp"), str(item.get("track_id")))
                    )
                except json.JSONDecodeError:
                    continue

    new_rows = [
        row for row in rows
        if (row["timestamp"], str(row["track_id"])) not in existing_keys
    ]

    if new_rows:
        with jsonl_path.open("a", encoding="utf-8") as handle:
            for row in new_rows:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")

        csv_exists = csv_path.exists() and csv_path.stat().st_size > 0
        with csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if not csv_exists:
                writer.writeheader()
            writer.writerows(new_rows)

    return len(new_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geojson", nargs="?", default="data/derived/live_objects.geojson")
    parser.add_argument("--jsonl", default="data/derived/live_object_history.jsonl")
    parser.add_argument("--csv", default="data/derived/live_object_history.csv")
    args = parser.parse_args()

    count = append_history(
        Path(args.geojson),
        Path(args.jsonl),
        Path(args.csv),
    )
    print(f"Appended {count} new object-timestep record(s).")


if __name__ == "__main__":
    main()
