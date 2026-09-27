"""Leakage-aware future-event target construction."""
from __future__ import annotations
import pandas as pd

def add_lead_time_target(df, onset_col="truth_onset_time", scan_col="scan_time", horizon_minutes=30):
    out = df.copy()
    out[onset_col] = pd.to_datetime(out[onset_col], utc=True, errors="coerce")
    out[scan_col] = pd.to_datetime(out[scan_col], utc=True, errors="coerce")
    delta = (out[onset_col] - out[scan_col]).dt.total_seconds() / 60.0
    out["lead_time_min"] = delta
    out[f"snow_squall_{horizon_minutes}min"] = (
        delta.ge(0) & delta.le(horizon_minutes)
    ).astype("int8")
    return out

def add_multi_horizon_targets(df, onset_col="truth_onset_time", scan_col="scan_time",
                              horizons=(15, 30, 45, 60)):
    out = df.copy()
    out[onset_col] = pd.to_datetime(out[onset_col], utc=True, errors="coerce")
    out[scan_col] = pd.to_datetime(out[scan_col], utc=True, errors="coerce")
    delta = (out[onset_col] - out[scan_col]).dt.total_seconds() / 60.0
    for horizon in horizons:
        out[f"snow_squall_{horizon}min"] = (
            delta.ge(0) & delta.le(horizon)
        ).astype("int8")
    return out

def exclude_leakage_columns(columns):
    forbidden = {
        "truth_onset_time", "truth_end_time", "sqw_intersection",
        "manual_label", "label_confidence", "label_source", "lead_time_min",
        "snow_squall_15min", "snow_squall_30min",
        "snow_squall_45min", "snow_squall_60min",
    }
    return [c for c in columns if c not in forbidden]
