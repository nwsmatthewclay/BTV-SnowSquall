"""Build leakage-safe forecast-time features from reconstructed object histories.

Every feature at time t uses only the current observation and observations
strictly before t. Future outcome/label columns are retained as outputs/metadata,
never as predictors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


OPERATIONAL_LIVE_PREDICTORS = {
    "area_km2", "length_km", "width_km", "aspect_ratio",
    "motion_dir_deg", "motion_speed_kt",
    "max_reflectivity_dbz", "mean_reflectivity_dbz",
    "core_pixel_count", "pixel_count", "core_fraction",
    "track_scan_index", "track_scan_count_to_date", "track_age_min",
    "track_gap_gt_10min", "centroid_displacement_km", "motion_speed_kmh",
    "max_reflectivity_dbz_delta", "max_reflectivity_dbz_rate_per_min",
    "mean_reflectivity_dbz_delta", "mean_reflectivity_dbz_rate_per_min",
    "area_km2_delta", "area_km2_rate_per_min",
    "length_km_delta", "length_km_rate_per_min",
    "width_km_delta", "width_km_rate_per_min",
    "max_reflectivity_dbz_running_max", "mean_reflectivity_dbz_running_max",
    "area_km2_running_max", "core_pixel_count_running_max", "pixel_count_running_max",
    "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient",
    "max_reflectivity_dbz_trailing_mean_3", "max_reflectivity_dbz_trailing_std_3",
    "max_reflectivity_dbz_change_2scan", "max_reflectivity_dbz_rate_2scan_per_min",
    "max_reflectivity_dbz_acceleration_per_min2",
    "area_km2_trailing_mean_3", "area_km2_trailing_std_3", "area_km2_change_2scan",
    "area_km2_rate_2scan_per_min", "area_km2_acceleration_per_min2",
    "echo_top_km_trailing_mean_3", "echo_top_km_trailing_std_3", "echo_top_km_change_2scan",
    "echo_top_km_rate_2scan_per_min", "echo_top_km_acceleration_per_min2",
    "motion_speed_kt_trailing_mean_3", "motion_speed_kt_trailing_std_3", "motion_speed_kt_change_2scan",
    "motion_speed_kt_rate_2scan_per_min", "motion_speed_kt_acceleration_per_min2",
    "track_persistence_min", "recent_scan_count_3",
    "vertical_valid_points", "zdr_mean_db", "zdr_p90_db", "zdr_gradient_dbkm",
    "rhohv_mean", "rhohv_max", "rhohv_p90", "rhohv_min",
    "kdp_mean_degkm", "kdp_p90_degkm", "velocity_mean_kt", "velocity_std_kt",
    "velocity_p90_abs_kt", "velocity_gradient_ktkm",
    "echo_top_km_delta", "echo_top_km_rate_per_min", "top_minus_base_km_delta", "top_minus_base_km_rate_per_min",
    "zdr_mean_db_delta", "zdr_mean_db_rate_per_min", "rhohv_mean_delta", "rhohv_mean_rate_per_min",
    "kdp_mean_degkm_delta", "kdp_mean_degkm_rate_per_min", "velocity_mean_kt_delta", "velocity_mean_kt_rate_per_min",
    "visibility_m", "gust_ms", "surface_temperature_k", "cape_jkg", "cin_jkg",
    "surface_wind_speed_kt", "shear_0_6km_kt", "temperature_dewpoint_spread_k",
    "cape_shear_product", "gust_excess_kt", "reflectivity_core_excess",
    "area_per_length", "shear_motion_ratio",
    "pwat_mm", "mlcape_jkg", "mlcin_jkg", "mucape_jkg", "mucin_jkg",
    "srh01_m2s2", "srh03_m2s2", "shear_u_0_6km_ms", "shear_v_0_6km_ms",
    "shear_0_6km_ms", "u10_ms", "v10_ms", "temperature_2m_k",
    "dewpoint_2m_k", "rh_2m_pct",
}

TARGET_COLUMNS = {
    "squall_onset_within_15m", "squall_onset_within_30m",
    "squall_onset_within_45m", "squall_onset_within_60m",
    "squall_ongoing_within_15m", "squall_ongoing_within_30m",
    "squall_ongoing_within_45m", "squall_ongoing_within_60m",
    "weak_onset_within_15m", "weak_onset_within_30m",
    "weak_onset_within_45m", "weak_onset_within_60m",
    "weak_sample_weight", "weak_label_status", "warning_iem_verified",
    "warning_issue_utc", "warning_distance_km", "lead_time_to_warning_min",
    "warning_verifying_lsr_count", "warning_supervision_class",
    "label_status", "label_reason",
    "label_confidence_15m", "label_confidence_30m",
    "label_confidence_45m", "label_confidence_60m",
    "track_event_distance_km", "track_event_associated",
    "case_station_distance_km", "association_method",
}

BLOCKED_PREFIXES = (
    "case_",
    "label_",
    "squall_",
    "track_event_",
    "association_",
    "surface_",
    "truth_",
)

NON_PREDICTOR_COLUMNS = TARGET_COLUMNS | {
    # Derived from verified future event timing; never a forecast-time predictor.
    "lead_time_min",
    # Official SQW intersection is truth/evidence metadata, not a model input.
    "sqw_intersection",
    # Surface observations are independent truth/QC inputs in v1, not
    # forecast-time predictors. They describe what happened at/after the event.
    "surface_observation",
    "visibility_sm",
    "snow_observed",
    "wind_gust_kt",
    "scan_time_utc", "source_file", "radar_site", "object_id",
    "population", "population_id", "population_source", "truth_status", "activity_class",
    "case_id", "null_id", "window_id", "episode_id", "source_study", "dataset_version",
    "future_information_policy", "population_track_key", "geometry_wkt", "truth_tier", "evidence_weight",
    "centroid_lat", "centroid_lon", "radar_lat", "radar_lon",
    "station_lat", "station_lon", "grid_x_km", "grid_y_km", "touches_grid_edge",
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

    group_cols = [c for c in ("population", "episode_id", "case_id", "null_id", "radar_site", "object_id") if c in df.columns]
    if not group_cols:
        group_cols = ["object_id"]
    df = df.sort_values(group_cols + ["scan_dt"]).reset_index(drop=True)
    g = df.groupby(group_cols, sort=False, dropna=False)

    df["track_scan_index"] = g.cumcount()
    df["track_scan_count_to_date"] = df["track_scan_index"] + 1
    first_time = g["scan_dt"].transform("min")
    df["track_age_min"] = (df["scan_dt"] - first_time).dt.total_seconds() / 60.0

    dt_min = (df["scan_dt"] - g["scan_dt"].shift(1)).dt.total_seconds() / 60.0
    continuity_ok = dt_min.between(0, 10, inclusive="both")
    df["track_gap_gt_10min"] = dt_min.gt(10).fillna(False)
    temporal_columns = [
        "max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2",
        "length_km", "width_km", "core_pixel_count", "pixel_count",
        "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient",
        "vertical_valid_points", "zdr_mean_db", "zdr_p90_db",
        "zdr_gradient_dbkm", "rhohv_mean", "rhohv_max", "rhohv_p90",
        "rhohv_min", "kdp_mean_degkm", "kdp_p90_degkm",
        "velocity_mean_kt", "velocity_std_kt", "velocity_p90_abs_kt",
        "velocity_gradient_ktkm",
    ]
    for col in temporal_columns:
        if col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            prev = pd.to_numeric(g[col].shift(1), errors="coerce")
            df[f"{col}_delta"] = (numeric - prev).where(continuity_ok)
            df[f"{col}_rate_per_min"] = (
                (numeric - prev) / dt_min.replace(0, np.nan)
            ).where(continuity_ok)

    # Multi-scan state uses only current and prior scans.
    previous_dt_min = (g["scan_dt"].shift(1) - g["scan_dt"].shift(2)).dt.total_seconds() / 60.0
    second_dt_min = (df["scan_dt"] - g["scan_dt"].shift(2)).dt.total_seconds() / 60.0
    continuity_2 = continuity_ok & previous_dt_min.between(0, 10, inclusive="both") & second_dt_min.between(0, 20, inclusive="both")
    for col in ("max_reflectivity_dbz", "area_km2", "echo_top_km", "motion_speed_kt"):
        if col not in df.columns:
            continue
        current = pd.to_numeric(df[col], errors="coerce")
        prev1 = pd.to_numeric(g[col].shift(1), errors="coerce")
        prev2 = pd.to_numeric(g[col].shift(2), errors="coerce")
        triple = pd.concat([current, prev1, prev2], axis=1)
        df[f"{col}_trailing_mean_3"] = triple.mean(axis=1, skipna=True)
        df[f"{col}_trailing_std_3"] = triple.std(axis=1, skipna=True)
        df[f"{col}_change_2scan"] = (current - prev2).where(continuity_2)
        df[f"{col}_rate_2scan_per_min"] = ((current - prev2) / second_dt_min.replace(0, np.nan)).where(continuity_2)
        prior_rate = ((prev1 - prev2) / previous_dt_min.replace(0, np.nan)).where(continuity_2)
        current_rate = ((current - prev1) / dt_min.replace(0, np.nan)).where(continuity_ok)
        df[f"{col}_acceleration_per_min2"] = (current_rate - prior_rate).where(continuity_2)
    df["track_persistence_min"] = df["track_age_min"].clip(lower=0)
    df["recent_scan_count_3"] = pd.concat([
        pd.Series(1, index=df.index),
        g["scan_dt"].shift(1).notna().astype(int),
        g["scan_dt"].shift(2).notna().astype(int),
    ], axis=1).sum(axis=1)

    if {"centroid_lat", "centroid_lon"}.issubset(df.columns):
        prev_lat = g["centroid_lat"].shift(1)
        prev_lon = g["centroid_lon"].shift(1)
        displacement = haversine_km(
            pd.to_numeric(prev_lat, errors="coerce"),
            pd.to_numeric(prev_lon, errors="coerce"),
            pd.to_numeric(df["centroid_lat"], errors="coerce"),
            pd.to_numeric(df["centroid_lon"], errors="coerce"),
        )
        df["centroid_displacement_km"] = displacement.where(continuity_ok)
        df["motion_speed_kmh"] = (
            displacement / dt_min.replace(0, np.nan) * 60.0
        ).where(continuity_ok)

    if {"u10_ms", "v10_ms"}.issubset(df.columns):
        wind = np.hypot(pd.to_numeric(df["u10_ms"], errors="coerce"), pd.to_numeric(df["v10_ms"], errors="coerce"))
        df["surface_wind_speed_kt"] = wind * 1.94384449244
    if {"shear_u_0_6km_ms", "shear_v_0_6km_ms"}.issubset(df.columns):
        shear = np.hypot(pd.to_numeric(df["shear_u_0_6km_ms"], errors="coerce"), pd.to_numeric(df["shear_v_0_6km_ms"], errors="coerce"))
        df["shear_0_6km_kt"] = shear * 1.94384449244
    if {"temperature_2m_k", "dewpoint_2m_k"}.issubset(df.columns):
        df["temperature_dewpoint_spread_k"] = pd.to_numeric(df["temperature_2m_k"], errors="coerce") - pd.to_numeric(df["dewpoint_2m_k"], errors="coerce")
    if {"cape_jkg", "shear_0_6km_kt"}.issubset(df.columns):
        df["cape_shear_product"] = pd.to_numeric(df["cape_jkg"], errors="coerce") * pd.to_numeric(df["shear_0_6km_kt"], errors="coerce")
    if {"gust_ms", "surface_wind_speed_kt"}.issubset(df.columns):
        df["gust_excess_kt"] = pd.to_numeric(df["gust_ms"], errors="coerce") * 1.94384449244 - pd.to_numeric(df["surface_wind_speed_kt"], errors="coerce")
    if {"max_reflectivity_dbz", "mean_reflectivity_dbz"}.issubset(df.columns):
        df["reflectivity_core_excess"] = pd.to_numeric(df["max_reflectivity_dbz"], errors="coerce") - pd.to_numeric(df["mean_reflectivity_dbz"], errors="coerce")
    if {"area_km2", "length_km"}.issubset(df.columns):
        length = pd.to_numeric(df["length_km"], errors="coerce").replace(0, np.nan)
        df["area_per_length"] = pd.to_numeric(df["area_km2"], errors="coerce") / length
    if {"shear_0_6km_kt", "motion_speed_kt"}.issubset(df.columns):
        motion = pd.to_numeric(df["motion_speed_kt"], errors="coerce").abs().replace(0, np.nan)
        df["shear_motion_ratio"] = pd.to_numeric(df["shear_0_6km_kt"], errors="coerce") / motion

    for col in [
        "max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2",
        "core_pixel_count", "pixel_count",
    ]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            df[f"{col}_running_max"] = s.groupby(
                [df[c] for c in group_cols], dropna=False
            ).cummax()

    keep = [c for c in df.columns if c not in TARGET_COLUMNS and c != "scan_dt"]
    target_outputs = [c for c in df.columns if c in TARGET_COLUMNS]
    return df[keep + target_outputs]


def predictor_columns(frame: pd.DataFrame) -> list[str]:
    columns = []
    for col in frame.columns:
        if col in NON_PREDICTOR_COLUMNS or col.startswith(BLOCKED_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(frame[col]):
            columns.append(col)
    return columns


def write_schema(frame: pd.DataFrame, schema_path: Path):
    schema = {
        "schema_version": "model_features_v1",
        "future_information_policy": "current_and_past_only",
        "location_predictor_policy": "excluded_from_baseline",
        "predictor_columns": predictor_columns(frame),
        "operational_predictor_columns": [c for c in predictor_columns(frame) if c in OPERATIONAL_LIVE_PREDICTORS],
        "blocked_non_predictors": sorted(NON_PREDICTOR_COLUMNS),
        "blocked_prefixes": list(BLOCKED_PREFIXES),
        "target_columns": sorted(TARGET_COLUMNS & set(frame.columns)),
    }
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return schema


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--schema-output",
        default=None,
        help="JSON schema path; defaults beside --output.",
    )
    args = parser.parse_args()

    source = pd.read_csv(args.input_csv)
    result = build_features(source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    schema_path = (
        Path(args.schema_output)
        if args.schema_output
        else output.with_suffix(".schema.json")
    )
    schema = write_schema(result, schema_path)

    print(f"Wrote {len(result)} forecast-time feature records to {output}")
    print(f"Predictor columns: {len(schema['predictor_columns'])}")
    print(f"Target/output columns: {len(schema['target_columns'])}")
    print(f"Future-information policy: {schema['future_information_policy']}")


if __name__ == "__main__":
    main()
