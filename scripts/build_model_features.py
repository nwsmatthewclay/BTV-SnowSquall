"""Build leakage-safe forecast-time features from reconstructed object histories.

Every feature at time t uses only the current observation and observations
strictly before t. Future outcome/label columns are never used as predictors.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


TARGET_COLUMNS = {
    "squall_onset_within_15m", "squall_onset_within_30m",
    "squall_onset_within_45m", "squall_onset_within_60m",
    "squall_ongoing_within_15m", "squall_ongoing_within_30m",
    "squall_ongoing_within_45m", "squall_ongoing_within_60m",
    "label_status", "label_reason", "label_confidence_15m",
    "label_confidence_30m", "label_confidence_45m", "label_confidence_60m",
    "track_event_distance_km", "track_event_associated",
    "case_station_distance_km", "association_method",
}


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 6371.0 * 2.0 * np.arcsin(np.sqrt(a))


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["scan_dt"] = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["scan_dt", "object_id"]).copy()

    group_cols = [c for c in ["population", "radar_site", "object_id"] if c in df.columns]
    if not group_cols:
        group_cols = ["object_id"]
    df = df.sort_values(group_cols + ["scan_dt"]).reset_index(drop=True)
    g = df.groupby(group_cols, sort=False, dropna=False)

    # Track-age/history features are causal: they describe what has happened
    # up through the current scan only.
    df["track_scan_index"] = g.cumcount()
    df["track_scan_count_to_date"] = df["track_scan_index"] + 1
    first_time = g["scan_dt"].transform("min")
    df["track_age_min"] = (df["scan_dt"] - first_time).dt.total_seconds() / 60.0

    for col in ["max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2",
                "length_km", "width_km", "core_pixel_count", "pixel_count"]:
        if col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            prev = g[col].shift(1)
            prev = pd.to_numeric(prev, errors="coerce")
            dt_min = (df["scan_dt"] - g["scan_dt"].shift(1)).dt.total_seconds() / 60.0
            df[f"{col}_delta"] = numeric - prev
            df[f"{col}_rate_per_min"] = (numeric - prev) / dt_min.replace(0, np.nan)

    if {"centroid_lat", "centroid_lon"}.issubset(df.columns):
        prev_lat = g["centroid_lat"].shift(1)
        prev_lon = g["centroid_lon"].shift(1)
        dt_min = (df["scan_dt"] - g["scan_dt"].shift(1)).dt.total_seconds() / 60.0
        df["centroid_displacement_km"] = haversine_km(
            pd.to_numeric(prev_lat, errors="coerce"),
            pd.to_numeric(prev_lon, errors="coerce"),
            pd.to_numeric(df["centroid_lat"], errors="coerce"),
            pd.to_numeric(df["centroid_lon"], errors="coerce"),
        )
        df["motion_speed_kmh"] = df["centroid_displacement_km"] / dt_min.replace(0, np.nan) * 60.0

    # Causal running maxima/minima capture storm evolution without peeking
    # beyond the current scan.
    for col in ["max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2",
                "core_pixel_count", "pixel_count"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            df[f"{col}_running_max"] = s.groupby(
                [df[c] for c in group_cols], dropna=False
            ).cummax()

    # Preserve environment predictors but explicitly exclude target/association
    # fields and identifiers that should never become model predictors.
    keep = []
    for col in df.columns:
        if col in TARGET_COLUMNS:
            continue
        if col in {"scan_dt"}:
            continue
        keep.append(col)

    # Environment variables are retained by name; this supports NARR/RUC/RAP
    # differences without pretending their fields are identical.
    df = df[keep + [c for c in TARGET_COLUMNS if c in df.columns]]
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = pd.read_csv(args.input_csv)
    result = build_features(source)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)

    print(f"Wrote {len(result)} forecast-time feature records to {args.output}")
    print("Feature columns:", len(result.columns))
    print("Future-information policy: current_and_past_only")


if __name__ == "__main__":
    main()
