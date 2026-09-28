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


def add_motion_features(frame, group_col="object_id", time_col="scan_time_utc"):
    """Add past-to-current motion only; no future information is used."""
    out = frame.copy()
    out[time_col] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    out = out.sort_values([group_col, time_col]).copy()
    groups = out.groupby(group_col, sort=False)

    out["prev_lat"] = groups["centroid_lat"].shift(1)
    out["prev_lon"] = groups["centroid_lon"].shift(1)
    out["prev_time"] = groups[time_col].shift(1)

    dt_min = (out[time_col] - out["prev_time"]).dt.total_seconds() / 60.0
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
    return out.drop(columns=["prev_lat", "prev_lon", "prev_time"])
