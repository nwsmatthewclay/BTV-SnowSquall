"""Translate live object history records into the leakage-safe model feature schema.

The adapter derives forecast-time predictors only from the current observation and
earlier observations for the same track. Unavailable fields remain null.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from snow_squall.evolution import add_environment_evolution_features


LIVE_TO_MODEL = {
    "reflectivity_max_dbz": "max_reflectivity_dbz",
    "reflectivity_mean_dbz": "mean_reflectivity_dbz",
    "wind_gust_kt": "gust_ms",
    "visibility_sm": "visibility_m",
    "sbcape_jkg": "cape_jkg",
    "sbcin_jkg": "cin_jkg",
}


def _number(value):
    try:
        if value is None or pd.isna(value):
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _utc(value):
    if value is None:
        return None
    try:
        return pd.to_datetime(value, utc=True)
    except Exception:
        return None


def _kt_from_ms(value):
    value = _number(value)
    return None if value is None else value * 1.943844492


def _mi_from_m(value):
    value = _number(value)
    return None if value is None else value / 1609.344


def build_live_feature_row(
    current: dict,
    previous: dict | None = None,
    track_count: int | None = None,
) -> dict:
    row = {"timestamp": current.get("timestamp"), "track_id": current.get("track_id")}

    for target, source in LIVE_TO_MODEL.items():
        row[target] = _number(current.get(source))

    for key in (
        "area_km2",
        "length_km",
        "width_km",
        "aspect_ratio",
        "orientation_deg",
        "motion_dir_deg",
        "motion_direction_deg",
        "motion_speed_kt",
        "aspect_ratio",
        "max_reflectivity_dbz",
        "mean_reflectivity_dbz",
        "core_pixel_count",
        "pixel_count",
        "core_fraction",
        "age_scans",
        "echo_top_km",
        "top_minus_base_km",
        "vertical_reflectivity_gradient",
        "vertical_valid_points",
        "zdr_mean_db",
        "zdr_p90_db",
        "zdr_gradient_dbkm",
        "rhohv_mean",
        "rhohv_max",
        "rhohv_p90",
        "rhohv_min",
        "kdp_mean_degkm",
        "kdp_p90_degkm",
        "velocity_mean_kt",
        "velocity_std_kt",
        "velocity_p90_abs_kt",
        "velocity_gradient_ktkm",        "snsq",
        "mean_rh_0_2km_pct",
        "thetae_delta_0_2km_k",
        "mean_wind_0_2km_ms",
        "wetbulb_2m_c",
        "snsq_moisture_factor",
        "snsq_instability_factor",
        "snsq_wind_factor",
        # Environmental predictors produced by the historical feature builder.
        "frontogenesis",
        "dcva",
        "omega",
        "epv",
        "cloud_layer_depth_m",
        "cloud_layer_rh_pct",
        "cloud_layer_mean_wind_kt",
        "cloud_layer_shear_kt",
    ):
        if key in current:
            row[key] = _number(current.get(key))

    # Preserve legacy aliases used by replay/tests.
    row["reflectivity_max_dbz"] = row.get("max_reflectivity_dbz")
    row["reflectivity_mean_dbz"] = row.get("mean_reflectivity_dbz")
    row["wind_gust_kt"] = _kt_from_ms(current.get("gust_ms"))
    row["visibility_sm"] = _mi_from_m(current.get("visibility_m"))
    row["sbcape_jkg"] = _number(current.get("cape_jkg"))
    row["sbcin_jkg"] = _number(current.get("cin_jkg"))

    # Canonical motion naming used by the historical feature builder.
    if row.get("motion_dir_deg") is None:
        row["motion_dir_deg"] = _number(current.get("motion_direction_deg"))
    row["motion_speed_kt"] = _number(current.get("motion_speed_kt"))
    row["aspect_ratio"] = _number(current.get("aspect_ratio"))
    # Backward-compatible aliases retained for existing contract tests/tools.
    row["reflectivity_max_dbz"] = _number(current.get("max_reflectivity_dbz"))
    row["reflectivity_mean_dbz"] = _number(current.get("mean_reflectivity_dbz"))

    # Environment fields flattened into the live history.
    for key in (
        "mlcape_jkg",
        "mlcin_jkg",
        "mucape_jkg",
        "mucin_jkg",
        "pwat_mm",
        "srh01_m2s2",
        "srh03_m2s2",
        "shear_u_0_6km_ms",
        "shear_v_0_6km_ms",
        "shear_0_6km_ms",
        "u10_ms",
        "v10_ms",
        "temperature_2m_k",
        "dewpoint_2m_k",
        "rh_2m_pct",
        "gust_ms",
        "visibility_m",
        "cape_jkg",
        "cin_jkg",
        "surface_temperature_k",
        "echo_top_km",
        "top_minus_base_km",
        "vertical_reflectivity_gradient",
        "vertical_valid_points",
        "zdr_mean_db",
        "zdr_p90_db",
        "zdr_gradient_dbkm",
        "rhohv_mean",
        "rhohv_max",
        "rhohv_p90",
        "rhohv_min",
        "kdp_mean_degkm",
        "kdp_p90_degkm",
        "velocity_mean_kt",
        "velocity_std_kt",
        "velocity_p90_abs_kt",
        "velocity_gradient_ktkm",
    ):
        if key in current:
            row[key] = _number(current.get(key))

    # Unit-safe derived fields.
    row["visibility_sm"] = _mi_from_m(current.get("visibility_m"))
    row["wind_gust_kt"] = _kt_from_ms(current.get("gust_ms"))

    u10 = _number(current.get("u10_ms"))
    v10 = _number(current.get("v10_ms"))
    if u10 is not None and v10 is not None:
        row["surface_wind_speed_kt"] = math.hypot(u10, v10) * 1.943844492

    su = _number(current.get("shear_u_0_6km_ms"))
    sv = _number(current.get("shear_v_0_6km_ms"))
    if su is not None and sv is not None:
        row["shear_0_6km_kt"] = math.hypot(su, sv) * 1.943844492
    else:
        row["shear_0_6km_kt"] = _kt_from_ms(current.get("shear_0_6km_ms"))

    temp = _number(current.get("temperature_2m_k"))
    dew = _number(current.get("dewpoint_2m_k"))
    if temp is not None and dew is not None:
        row["temperature_dewpoint_spread_k"] = temp - dew

    cape = _number(current.get("cape_jkg"))
    if cape is not None and row.get("shear_0_6km_kt") is not None:
        row["cape_shear_product"] = cape * row["shear_0_6km_kt"]

    gust_kt = row.get("wind_gust_kt")
    surface_wind_kt = row.get("surface_wind_speed_kt")
    if gust_kt is not None and surface_wind_kt is not None:
        row["gust_excess_kt"] = gust_kt - surface_wind_kt

    max_z = _number(current.get("max_reflectivity_dbz"))
    mean_z = _number(current.get("mean_reflectivity_dbz"))
    area = _number(current.get("area_km2"))
    length = _number(current.get("length_km"))
    motion = _number(current.get("motion_speed_kt"))
    if max_z is not None and mean_z is not None:
        row["reflectivity_core_excess"] = max_z - mean_z
    if area is not None and length not in (None, 0):
        row["area_per_length"] = area / length
    if row.get("shear_0_6km_kt") is not None and motion not in (None, 0):
        row["shear_motion_ratio"] = row["shear_0_6km_kt"] / abs(motion)

    if row.get("max_reflectivity_dbz_rate_per_min") is not None and row.get("cape_jkg") is not None:
        row["cape_weighted_reflectivity_growth"] = (
            row["max_reflectivity_dbz_rate_per_min"]
            * max(0.0, row["cape_jkg"])
            / 100.0
        )
    if row.get("max_reflectivity_dbz_rate_per_min") is not None and row.get("mean_rh_0_2km_pct") is not None:
        row["moisture_weighted_reflectivity_growth"] = (
            row["max_reflectivity_dbz_rate_per_min"]
            * row["mean_rh_0_2km_pct"]
            / 100.0
        )
    if row.get("area_km2_rate_per_min") is not None and row.get("shear_0_6km_kt") is not None:
        row["shear_weighted_area_growth"] = (
            row["area_km2_rate_per_min"]
            * row["shear_0_6km_kt"]
        )

    current_time = _utc(current.get("timestamp"))
    previous_time = _utc(previous.get("timestamp")) if previous else None
    dt_min = None
    if current_time is not None and previous_time is not None:
        dt_min = (current_time - previous_time).total_seconds() / 60.0
    continuity = dt_min is not None and 0 < dt_min <= 10

    row["track_gap_gt_10min"] = bool(dt_min is not None and dt_min > 10.0)

    if previous and continuity:
        pairs = (
            ("max_reflectivity_dbz", "max_reflectivity_dbz_delta"),
            ("mean_reflectivity_dbz", "mean_reflectivity_dbz_delta"),
            ("area_km2", "area_km2_delta"),
            ("length_km", "length_km_delta"),
            ("width_km", "width_km_delta"),
            ("echo_top_km", "echo_top_km_delta"),
            ("top_minus_base_km", "top_minus_base_km_delta"),
            ("zdr_mean_db", "zdr_mean_db_delta"),
            ("rhohv_mean", "rhohv_mean_delta"),
            ("kdp_mean_degkm", "kdp_mean_degkm_delta"),
            ("velocity_mean_kt", "velocity_mean_kt_delta"),
        )
        for source, target in pairs:
            a = _number(current.get(source))
            b = _number(previous.get(source))
            if a is not None and b is not None:
                delta = a - b
                row[target] = delta
                row[target.replace("_delta", "_rate_per_min")] = delta / dt_min

        current_lat = _number(current.get("centroid_lat"))
        current_lon = _number(current.get("centroid_lon"))
        previous_lat = _number(previous.get("centroid_lat"))
        previous_lon = _number(previous.get("centroid_lon"))
        if None not in (current_lat, current_lon, previous_lat, previous_lon):
            lat1 = math.radians(current_lat)
            lon1 = math.radians(current_lon)
            lat2 = math.radians(previous_lat)
            lon2 = math.radians(previous_lon)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (
                math.sin(dlat / 2.0) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
            )
            displacement = 6371.0 * 2.0 * math.asin(min(1.0, math.sqrt(a)))
            row["centroid_displacement_km"] = displacement
            row["motion_speed_kmh"] = displacement / dt_min * 60.0

    if track_count is not None:
        row["track_scan_count_to_date"] = int(track_count)
        row["track_scan_index"] = int(track_count) - 1

    return row


def build_live_feature_frame(history: Iterable[dict], track_id: str | int) -> pd.DataFrame:
    rows = [dict(r) for r in history if str(r.get("track_id")) == str(track_id)]
    rows.sort(key=lambda r: str(r.get("timestamp", "")))

    features = []
    first_timestamp = rows[0].get("timestamp") if rows else None
    running = {
        "max_reflectivity_dbz": None,
        "mean_reflectivity_dbz": None,
        "area_km2": None,
        "core_pixel_count": None,
        "pixel_count": None,
    }

    for idx, current in enumerate(rows):
        previous = rows[idx - 1] if idx else None
        row = build_live_feature_row(
            current,
            previous=previous,
            track_count=idx + 1,
        )

        current_time = _utc(current.get("timestamp"))
        first_time = _utc(first_timestamp)
        row["track_age_min"] = (
            max(0.0, (current_time - first_time).total_seconds() / 60.0)
            if current_time is not None and first_time is not None
            else None
        )

        row["track_persistence_min"] = row.get("track_age_min")
        row["recent_scan_count_3"] = min(idx + 1, 3)

        # Three-scan trailing state mirrors the historical feature builder.
        if idx >= 2:
            prev2 = rows[idx - 2]
            prev2_time = _utc(prev2.get("timestamp"))
            if current_time is not None and prev2_time is not None:
                dt2 = (current_time - prev2_time).total_seconds() / 60.0
                previous_time = _utc(previous.get("timestamp")) if previous is not None else None
                prev_dt = (previous_time - prev2_time).total_seconds() / 60.0 if previous_time is not None else None
                if 0 < dt2 <= 20 and prev_dt is not None and 0 < prev_dt <= 10:
                    for source in ("max_reflectivity_dbz", "area_km2", "echo_top_km", "motion_speed_kt"):
                        vals = [_number(prev2.get(source)), _number(current.get(source)), _number(previous.get(source))]
                        finite = [v for v in vals if v is not None]
                        if finite:
                            row[source + "_trailing_mean_3"] = sum(finite) / len(finite)
                            if len(finite) >= 2:
                                mean = sum(finite) / len(finite)
                                row[source + "_trailing_std_3"] = (sum((v - mean) ** 2 for v in finite) / (len(finite) - 1)) ** 0.5
                        old = _number(prev2.get(source))
                        cur = _number(current.get(source))
                        if old is not None and cur is not None:
                            row[source + "_change_2scan"] = cur - old
                            row[source + "_rate_2scan_per_min"] = (cur - old) / dt2
                        p = _number(previous.get(source))
                        if old is not None and p is not None and cur is not None:
                            current_dt = (current_time - previous_time).total_seconds() / 60.0
                            if 0 < current_dt <= 10:
                                row[source + "_acceleration_per_min2"] = ((cur - p) / current_dt) - ((p - old) / prev_dt)

        for source, target in (
            ("max_reflectivity_dbz", "max_reflectivity_dbz_running_max"),
            ("mean_reflectivity_dbz", "mean_reflectivity_dbz_running_max"),
            ("area_km2", "area_km2_running_max"),
            ("core_pixel_count", "core_pixel_count_running_max"),
            ("pixel_count", "pixel_count_running_max"),
        ):
            value = _number(current.get(source))
            prior = running[source]
            if value is not None:
                running[source] = value if prior is None else max(prior, value)
            row[target] = running[source]

        features.append(row)

    frame = pd.DataFrame(features)
    if frame.empty:
        return frame

    # Apply exactly the same causal environmental-evolution transform used by
    # historical training. The live frame is already restricted to one track.
    frame = add_environment_evolution_features(
        frame,
        group_cols=["track_id"],
        time_col="timestamp",
    )
    return frame


def feature_coverage(frame: pd.DataFrame, predictor_columns: Iterable[str]) -> dict:
    columns = list(predictor_columns)
    if not columns:
        return {"predictors": 0, "available": 0, "fraction": 0.0, "missing": []}

    available = [c for c in columns if c in frame.columns and frame[c].notna().any()]
    missing = [c for c in columns if c not in available]
    return {
        "predictors": len(columns),
        "available": len(available),
        "fraction": round(len(available) / len(columns), 3),
        "missing": missing,
    }
