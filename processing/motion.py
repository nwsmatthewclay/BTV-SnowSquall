"""Compute leakage-safe storm-object motion from geographic centroids."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def add_motion_features(frame, group_col="object_id"):
    """Add past-to-current motion only; isolate simultaneous radar sites."""
    out = frame.copy()
    out["scan_time_utc"] = pd.to_datetime(out["scan_time_utc"], utc=True, errors="coerce")

    if "radar_site" in out.columns:
        motion_group = out["radar_site"].astype(str) + ":" + out[group_col].astype(str)
    else:
        motion_group = out[group_col].astype(str)

    out["_motion_group"] = motion_group
    out = out.sort_values(["_motion_group", "scan_time_utc"]).copy()
    groups = out.groupby("_motion_group", sort=False)

    out["prev_lat"] = groups["centroid_lat"].shift(1)
    out["prev_lon"] = groups["centroid_lon"].shift(1)
    out["prev_time"] = groups["scan_time_utc"].shift(1)

    dt_min = (out["scan_time_utc"] - out["prev_time"]).dt.total_seconds() / 60.0
    distance_km = _haversine_km(
        out["prev_lat"], out["prev_lon"], out["centroid_lat"], out["centroid_lon"]
    )
    out["motion_distance_km"] = distance_km.where(dt_min > 0)
    out["motion_speed_kt"] = (distance_km / (dt_min / 60.0) / 1.852).where(dt_min > 0)

    lat1 = np.radians(out["prev_lat"])
    lat2 = np.radians(out["centroid_lat"])
    dlon = np.radians(out["centroid_lon"] - out["prev_lon"])
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    out["motion_direction_deg"] = (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0
    direction_rad = np.radians(out["motion_direction_deg"])
    out["motion_u_kt"] = out["motion_speed_kt"] * np.sin(direction_rad)
    out["motion_v_kt"] = out["motion_speed_kt"] * np.cos(direction_rad)

    if "radar_motion_speed_kt" in out.columns:
        radar_speed = pd.to_numeric(out["radar_motion_speed_kt"], errors="coerce")
        out["motion_speed_minus_radar_kt"] = out["motion_speed_kt"] - radar_speed
    if "radar_motion_direction_deg" in out.columns:
        radar_dir = pd.to_numeric(out["radar_motion_direction_deg"], errors="coerce")
        out["motion_direction_error_deg"] = (
            (out["motion_direction_deg"] - radar_dir + 180.0) % 360.0 - 180.0
        ).abs()
    if {"motion_u_kt","motion_v_kt","radar_motion_u_kt","radar_motion_v_kt"}.issubset(out.columns):
        denom = (
            np.hypot(out["motion_u_kt"], out["motion_v_kt"])
            * np.hypot(out["radar_motion_u_kt"], out["radar_motion_v_kt"])
        )
        out["motion_radar_alignment"] = (
            (
                out["motion_u_kt"] * out["radar_motion_u_kt"]
                + out["motion_v_kt"] * out["radar_motion_v_kt"]
            ) / denom.replace(0, np.nan)
        )

    return out.drop(columns=["prev_lat", "prev_lon", "prev_time", "_motion_group"])
