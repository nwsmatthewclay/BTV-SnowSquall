"""Environment normalization and nearest-analysis attachment."""
from __future__ import annotations
import pandas as pd

ENVIRONMENT_COLUMNS = [
    "snsqu", "sbcape_jkg", "mucape_jkg", "mlcape_jkg", "sbcin_jkg",
    "mlcin_jkg", "dcape_jkg", "pwat_mm", "lcl_m", "rh_0_2km_pct",
    "wind_0_1km_kt", "wind_0_3km_kt", "shear_0_1km_kt",
    "shear_0_3km_kt", "shear_0_6km_kt", "lr_0_3_c_km",
    "lr_0_7p5_c_km", "wetbulb_0_3_c", "frontogenesis", "dcva",
    "omega", "epv",
]

def normalize_environment_frame(frame):
    out = frame.copy()
    for col in ENVIRONMENT_COLUMNS:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "analysis_time_utc" in out:
        out["analysis_time_utc"] = pd.to_datetime(out["analysis_time_utc"], utc=True)
    return out

def nearest_environment(objects, environment):
    left = objects.copy()
    right = normalize_environment_frame(environment)
    left["scan_time"] = pd.to_datetime(left["scan_time"], utc=True)
    left = left.sort_values("scan_time")
    right = right.sort_values("analysis_time_utc")
    return pd.merge_asof(left, right, left_on="scan_time",
                         right_on="analysis_time_utc", direction="nearest",
                         suffixes=("", "_env"))
