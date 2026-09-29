"""Translate live object history records into the leakage-safe model feature schema.

The adapter is deliberately conservative: it only derives values from the current
record and earlier records for the same track. Unavailable fields remain null.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Iterable

import pandas as pd


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


def build_live_feature_row(current: dict, previous: dict | None = None, track_count: int | None = None) -> dict:
    row = {}

    for target, source in LIVE_TO_MODEL.items():
        row[target] = _number(current.get(source))

    for key in (
        "area_km2", "length_km", "width_km", "orientation_deg",
        "motion_dir_deg", "motion_speed_kt", "max_reflectivity_dbz",
        "mean_reflectivity_dbz", "core_pixel_count", "core_fraction",
        "age_scans",
    ):
        if key in current:
            row[key] = _number(current.get(key))

    # Canonical names used by the historical model-feature builder.
    row["area_km2"] = _number(current.get("area_km2"))
    row["length_km"] = _number(current.get("length_km"))
    row["width_km"] = _number(current.get("width_km"))
    row["motion_dir_deg"] = _number(current.get("motion_dir_deg", current.get("motion_direction_deg")))
    row["motion_speed_kt"] = _number(current.get("motion_speed_kt"))

    # Environment fields already flattened by append_live_object_history.py.
    for key in (
        "mlcape_jkg", "mlcin_jkg", "mucape_jkg", "mucin_jkg", "pwat_mm",
        "srh01_m2s2", "srh03_m2s2", "shear_u_0_6km_ms", "shear_v_0_6km_ms",
        "shear_0_6km_ms", "u10_ms", "v10_ms", "temperature_2m_k",
        "dewpoint_2m_k", "rh_2m_pct", "gust_ms", "visibility_m", "cape_jkg",
        "cin_jkg",
    ):
        if key in current:
            row[key] = _number(current.get(key))

    row["wind_gust_kt"] = _kt_from_ms(current.get("gust_ms"))
    row["shear_0_6km_kt"] = _kt_from_ms(current.get("shear_0_6km_ms"))

    # Common historical names expected by the feature schema.

    max_z = _number(current.get("max_reflectivity_dbz"))
    mean_z = _number(current.get("mean_reflectivity_dbz"))
    area = _number(current.get("area_km2"))
    length = _number(current.get("length_km"))
    motion = _number(current.get("motion_speed_kt"))
    shear = row.get("shear_0_6km_kt")

    if max_z is not None and mean_z is not None:
        row["reflectivity_core_excess"] = max_z - mean_z
    if area is not None and length not in (None, 0):
        row["area_per_length"] = area / length
    if shear is not None and motion is not None:
        row["shear_motion_ratio"] = shear / (abs(motion) + 1e-6)

    if previous:
        current_time = _utc(current.get("timestamp"))
        previous_time = _utc(previous.get("timestamp"))
        dt_min = None
        if current_time is not None and previous_time is not None:
            dt_min = (current_time - previous_time).total_seconds() / 60.0

        if dt_min is not None and 0 < dt_min <= 10:
            pairs = (
                ("max_reflectivity_dbz", "max_reflectivity_dbz_delta"),
                ("mean_reflectivity_dbz", "mean_reflectivity_dbz_delta"),
                ("area_km2", "area_km2_delta"),
                ("length_km", "length_km_delta"),
                ("width_km", "width_km_delta"),
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
                dlat = math.radians(current_lat - previous_lat)
                dlon = math.radians(current_lon - previous_lon)
                mean_lat = math.radians((current_lat + previous_lat) / 2.0)
                a = math.sin(dlat / 2.0) ** 2 + math.cos(mean_lat) * math.cos(mean_lat) * math.sin(dlon / 2.0) ** 2
                displacement = 6371.0 * 2.0 * math.asin(min(1.0, math.sqrt(a)))
                row["centroid_displacement_km"] = displacement
                row["motion_speed_kmh"] = displacement / dt_min * 60.0

    if track_count is not None:
        row["track_scan_count_to_date"] = int(track_count)
        if track_count > 0:
            row["track_scan_index"] = int(track_count) - 1

    return row


def build_live_feature_frame(history: Iterable[dict], track_id: str | int) -> pd.DataFrame:
    rows = [dict(r) for r in history if str(r.get("track_id")) == str(track_id)]
    rows.sort(key=lambda r: str(r.get("timestamp", "")))
    features = []
    for idx, current in enumerate(rows):
        previous = rows[idx - 1] if idx else None
        row = build_live_feature_row(current, previous=previous, track_count=idx + 1)
        features.append(row)
    return pd.DataFrame(features)


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
