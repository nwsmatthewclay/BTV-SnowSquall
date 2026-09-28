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

def object_field_summary(values, prefix: str, gradient=None, gradient_suffix: str = ""):
    """Summarize one gridded radar field over a candidate object's footprint."""
    arr = np.asarray(values, dtype=float)
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        result = {
            f"{prefix}_mean": np.nan,
            f"{prefix}_max": np.nan,
            f"{prefix}_p90": np.nan,
        }
    else:
        result = {
            f"{prefix}_mean": float(np.mean(valid)),
            f"{prefix}_max": float(np.max(valid)),
            f"{prefix}_p90": float(np.percentile(valid, 90)),
        }
    if gradient is not None:
        g = np.asarray(gradient, dtype=float)
        gvalid = g[np.isfinite(g)]
        result[f"{prefix}_gradient{gradient_suffix}"] = (
            float(np.mean(gvalid)) if gvalid.size else np.nan
        )
    return result

def velocity_object_summary(values, gradient=None):
    """Return descriptive radial-velocity texture; this is not bulk shear."""
    result = object_field_summary(values, "velocity", gradient)
    arr = np.asarray(values, dtype=float)
    valid = arr[np.isfinite(arr)]
    result["velocity_std_kt"] = float(np.std(valid)) if valid.size else np.nan
    abs_valid = np.abs(valid)
    result["velocity_p90_abs_kt"] = (
        float(np.percentile(abs_valid, 90)) if abs_valid.size else np.nan
    )
    return result
