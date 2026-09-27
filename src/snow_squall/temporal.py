"""Create leakage-safe temporal features from tracked radar objects."""
from __future__ import annotations
import pandas as pd

EVOLUTION_COLUMNS = {
    "max_reflectivity_dbz": "reflectivity",
    "echo_top_m": "echo_top",
    "area_km2": "area",
    "length_km": "length",
    "width_km": "width",
}

def add_track_history_features(frame, group_col="track_id", time_col="scan_time"):
    out = frame.copy()
    out[time_col] = pd.to_datetime(out[time_col], utc=True)
    out = out.sort_values([group_col, time_col])
    groups = out.groupby(group_col, sort=False)
    out["track_age_min"] = (
        out[time_col] - groups[time_col].transform("min")
    ).dt.total_seconds() / 60.0
    for source, stem in EVOLUTION_COLUMNS.items():
        if source not in out:
            continue
        values = pd.to_numeric(out[source], errors="coerce")
        out[f"{stem}_delta_5min"] = values - groups[source].shift(1)
        out[f"{stem}_delta_10min"] = values - groups[source].shift(2)
        out[f"{stem}_trend_5min"] = out[f"{stem}_delta_5min"]
    if "motion_speed_kt" in out:
        speed = pd.to_numeric(out["motion_speed_kt"], errors="coerce")
        out["motion_speed_delta"] = speed - groups["motion_speed_kt"].shift(1)
    return out

def make_sequence_windows(frame, group_col="track_id", time_col="scan_time",
                          lookback_scans=3):
    out = frame.copy()
    out[time_col] = pd.to_datetime(out[time_col], utc=True)
    out = out.sort_values([group_col, time_col])
    return [
        group.iloc[max(0, i - lookback_scans + 1):i + 1].copy()
        for _, group in out.groupby(group_col, sort=False)
        for i in range(len(group))
    ]
