"""Shared causal storm/environment evolution feature generation.

The same routine is used by historical feature construction and the live model
adapter so predictor semantics cannot drift between training and inference.
"""
from __future__ import annotations

from typing import Iterable
import numpy as np

import pandas as pd

ENVIRONMENTAL_EVOLUTION_COLUMNS = (
    "snsq",
    "cape_jkg",
    "mlcape_jkg",
    "mucape_jkg",
    "dcape_jkg",
    "pwat_mm",
    "srh01_m2s2",
    "srh03_m2s2",
    "shear_0_6km_ms",
    "mean_rh_0_2km_pct",
    "mean_wind_0_2km_ms",
    "thetae_delta_0_2km_k",
    "frontogenesis",
    "dcva",
    "omega",
    "epv",
)


def _add_group_temporal(
    out: pd.DataFrame,
    group,
    time_col: str,
    columns: Iterable[str],
    *,
    max_gap_minutes: float = 10.0,
) -> pd.DataFrame:
    out = out.copy()
    times = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    previous_times = pd.to_datetime(group[time_col].shift(1), utc=True, errors="coerce")
    previous2_times = pd.to_datetime(group[time_col].shift(2), utc=True, errors="coerce")
    dt_min = (times - previous_times).dt.total_seconds() / 60.0
    continuity = dt_min.between(0, max_gap_minutes, inclusive="both")

    previous_dt_min = (
        previous_times - previous2_times
    ).dt.total_seconds() / 60.0
    second_dt_min = (
        times - previous2_times
    ).dt.total_seconds() / 60.0
    continuity_2 = (
        continuity
        & previous_dt_min.between(0, max_gap_minutes, inclusive="both")
        & second_dt_min.between(0, max_gap_minutes * 2, inclusive="both")
    )

    for col in columns:
        if col not in out.columns:
            continue
        current = pd.to_numeric(out[col], errors="coerce")
        previous = pd.to_numeric(group[col].shift(1), errors="coerce")
        delta = (current - previous).where(continuity)
        out[f"{col}_delta"] = delta
        out[f"{col}_rate_per_min"] = (
            delta / dt_min.replace(0, pd.NA)
        ).where(continuity)

        prev2 = pd.to_numeric(group[col].shift(2), errors="coerce")
        triple = pd.concat([current, previous, prev2], axis=1)
        out[f"{col}_trailing_mean_3"] = triple.mean(axis=1, skipna=True).where(continuity_2)
        out[f"{col}_trailing_std_3"] = triple.std(axis=1, skipna=True).where(continuity_2)
        out[f"{col}_change_2scan"] = (current - prev2).where(continuity_2)
        out[f"{col}_rate_2scan_per_min"] = (
            (current - prev2) / second_dt_min.replace(0, pd.NA)
        ).where(continuity_2)

        prior_rate = (
            (previous - prev2) / previous_dt_min.replace(0, pd.NA)
        ).where(continuity_2)
        current_rate = (
            (current - previous) / dt_min.replace(0, pd.NA)
        ).where(continuity)
        out[f"{col}_acceleration_per_min2"] = (
            current_rate - prior_rate
        ).where(continuity_2)

    return out


def add_environment_evolution_features(
    frame: pd.DataFrame,
    *,
    group_cols: Iterable[str],
    time_col: str,
    columns: Iterable[str] = ENVIRONMENTAL_EVOLUTION_COLUMNS,
) -> pd.DataFrame:
    """Add past-only environmental trend/state features.

    Every derived value at time t uses t, t-1 and t-2 only. Large observation
    gaps reset the temporal derivatives to prevent artificial jumps.
    """
    out = frame.copy()
    group_cols = [c for c in group_cols if c in out.columns]
    if not group_cols or time_col not in out.columns:
        return out

    out = out.sort_values(group_cols + [time_col]).copy()
    group = out.groupby(group_cols, sort=False, dropna=False)
    return _add_group_temporal(
        out,
        group,
        time_col,
        columns,
    )


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = [np.asarray(x, dtype=float) for x in (lat1, lon1, lat2, lon2)]
    lat1, lat2 = np.radians(lat1), np.radians(lat2)
    dlat = lat2 - lat1
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2.0)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2.0)**2
    return 6371.0 * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _signed_angle_delta_deg(current, previous):
    delta = (current - previous + 180.0) % 360.0 - 180.0
    return delta


def add_motion_evolution_features(
    frame: pd.DataFrame,
    *,
    group_cols: Iterable[str],
    time_col: str,
    lat_col: str = "centroid_lat",
    lon_col: str = "centroid_lon",
) -> pd.DataFrame:
    """Add causal storm-motion evolution features.

    Direction changes use the shortest circular angular difference. Straightness
    uses the ratio of net displacement to the summed path length over up to the
    most recent three scans. Every feature at t uses only t, t-1 and t-2.
    """
    out = frame.copy()
    group_cols = [c for c in group_cols if c in out.columns]
    required = {"motion_speed_kt", "motion_dir_deg", time_col}
    if not group_cols or not required.issubset(out.columns):
        return out

    out = out.sort_values(group_cols + [time_col]).copy()
    group = out.groupby(group_cols, sort=False, dropna=False)

    times = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    prev_times = pd.to_datetime(group[time_col].shift(1), utc=True, errors="coerce")
    prev2_times = pd.to_datetime(group[time_col].shift(2), utc=True, errors="coerce")
    dt = (times - prev_times).dt.total_seconds() / 60.0
    dt_prev = (prev_times - prev2_times).dt.total_seconds() / 60.0
    contiguous = dt.between(0, 10, inclusive="both")
    contiguous2 = contiguous & dt_prev.between(0, 10, inclusive="both") & (
        (times - prev2_times).dt.total_seconds() / 60.0
    ).between(0, 20, inclusive="both")

    speed = pd.to_numeric(out["motion_speed_kt"], errors="coerce")
    prev_speed = pd.to_numeric(group["motion_speed_kt"].shift(1), errors="coerce")
    prev2_speed = pd.to_numeric(group["motion_speed_kt"].shift(2), errors="coerce")

    speed_delta = (speed - prev_speed).where(contiguous)
    out["motion_speed_kt_delta"] = speed_delta
    out["motion_speed_kt_rate_per_min"] = (
        speed_delta / dt.replace(0, np.nan)
    ).where(contiguous)

    speed_change2 = (speed - prev2_speed).where(contiguous2)
    out["motion_speed_kt_change_2scan"] = speed_change2
    out["motion_speed_kt_rate_2scan_per_min"] = (
        speed_change2 / ((times - prev2_times).dt.total_seconds() / 60.0).replace(0, np.nan)
    ).where(contiguous2)
    current_rate = (speed - prev_speed) / dt.replace(0, np.nan)
    previous_rate = (prev_speed - prev2_speed) / dt_prev.replace(0, np.nan)
    out["motion_speed_kt_acceleration_per_min2"] = (
        current_rate - previous_rate
    ).where(contiguous2)

    direction = pd.to_numeric(out["motion_dir_deg"], errors="coerce")
    prev_direction = pd.to_numeric(group["motion_dir_deg"].shift(1), errors="coerce")
    turn = _signed_angle_delta_deg(direction, prev_direction)
    turn = turn.where(contiguous)
    out["motion_turn_deg"] = turn
    out["motion_turn_rate_deg_per_min"] = (
        turn / dt.replace(0, np.nan)
    ).where(contiguous)

    prev_prev_direction = pd.to_numeric(group["motion_dir_deg"].shift(2), errors="coerce")
    prev_turn = _signed_angle_delta_deg(prev_direction, prev_prev_direction).where(contiguous2)
    # A mean cosine of recent turn angles: 1 = straight, 0 = highly variable.
    turn_rad = np.deg2rad(pd.concat([turn, prev_turn], axis=1))
    out["motion_persistence_3"] = (
        np.cos(turn_rad).mean(axis=1, skipna=True)
    ).where(contiguous2)

    if lat_col in out.columns and lon_col in out.columns:
        lat = pd.to_numeric(out[lat_col], errors="coerce")
        lon = pd.to_numeric(out[lon_col], errors="coerce")
        prev_lat = pd.to_numeric(group[lat_col].shift(1), errors="coerce")
        prev_lon = pd.to_numeric(group[lon_col].shift(1), errors="coerce")
        prev2_lat = pd.to_numeric(group[lat_col].shift(2), errors="coerce")
        prev2_lon = pd.to_numeric(group[lon_col].shift(2), errors="coerce")

        step1 = haversine_km(lat, lon, prev_lat, prev_lon)
        step2 = haversine_km(prev_lat, prev_lon, prev2_lat, prev2_lon)
        net3 = haversine_km(lat, lon, prev2_lat, prev2_lon)
        path3 = step1 + step2
        out["motion_path_length_3_km"] = path3.where(contiguous2)
        out["motion_straightness_3"] = (
            (net3 / path3.replace(0, np.nan)).clip(0, 1)
        ).where(contiguous2)

    max_z_rate = pd.to_numeric(out.get("max_reflectivity_dbz_rate_per_min"), errors="coerce")
    area_rate = pd.to_numeric(out.get("area_km2_rate_per_min"), errors="coerce")
    speed_floor = speed.clip(lower=1.0)
    if max_z_rate is not None:
        out["reflectivity_growth_per_motion"] = max_z_rate / speed_floor
    if area_rate is not None:
        out["area_growth_per_motion"] = area_rate / speed_floor

    return out
