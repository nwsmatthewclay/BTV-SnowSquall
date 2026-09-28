"""Radar feature extraction primitives."""
from __future__ import annotations
import numpy as np

def field_summary(values):
    arr = np.asarray(values, dtype=float)
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return {"count": 0, "mean": np.nan, "max": np.nan, "p90": np.nan}
    return {"count": int(valid.size), "mean": float(np.mean(valid)),
            "max": float(np.max(valid)), "p90": float(np.percentile(valid, 90))}

def robust_percentile(values, percentile=90.0):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(np.percentile(arr, percentile)) if arr.size else np.nan

def reflectivity_core_excess(reflectivity, core_threshold=40.0):
    arr = np.asarray(reflectivity, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not arr.size:
        return np.nan
    return float(np.percentile(arr, 90) - max(core_threshold, np.percentile(arr, 50)))

def vertical_depth(echo_top_m, echo_base_m=0.0):
    if echo_top_m is None:
        return np.nan
    return float(echo_top_m) - float(echo_base_m)
