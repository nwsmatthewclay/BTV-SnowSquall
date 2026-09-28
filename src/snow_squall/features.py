"""Feature engineering utilities for radar-object/environment observations."""
from __future__ import annotations
import math
import pandas as pd

TARGET_COLUMN = "snow_squall_30min"

BASE_FEATURES = [
    "snsq","sbcape_jkg","mucape_jkg","mlcape_jkg","sbcin_jkg","mlcin_jkg",
    "dcape_jkg","pwat_mm","lcl_m","rh_0_2km_pct","wind_0_1km_kt",
    "wind_0_3km_kt","shear_0_1km_kt","shear_0_3km_kt","shear_0_6km_kt",
    "lapse_rate_0_3km_c_km","lapse_rate_0_7_5km_c_km","wet_bulb_0_3km_c",
    "frontogenesis","dcva","omega","epv","reflectivity_max_dbz",
    "reflectivity_mean_dbz","echo_top_km","top_minus_base_km",
    "velocity_delta_0_6km_kt","zdr_mean_db","rhohv_mean","kdp_mean_degkm",
    "mrms_reflectivity_dbz","mrms_precip_rate","mrms_snow_rate",
    "object_growth_pct_10min","reflectivity_change_db_10min",
    "echo_top_change_km_10min","motion_speed_kt","area_km2","length_km","width_km"
]

def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    out=df.copy()
    if {"area_km2","length_km"}.issubset(out):
        # Preserve exact ratios for ordinary positive lengths while avoiding
        # division by zero for malformed/degenerate objects.
        length = pd.to_numeric(out["length_km"], errors="coerce")
        area = pd.to_numeric(out["area_km2"], errors="coerce")
        out["area_per_length"] = area.div(length.where(length != 0))
    if {"reflectivity_max_dbz","reflectivity_mean_dbz"}.issubset(out):
        out["reflectivity_core_excess"]=out["reflectivity_max_dbz"]-out["reflectivity_mean_dbz"]
    if {"shear_0_6km_kt","motion_speed_kt"}.issubset(out):
        out["shear_motion_ratio"]=out["shear_0_6km_kt"]/(out["motion_speed_kt"].abs()+eps)
    if {"object_growth_pct_10min","reflectivity_change_db_10min"}.issubset(out):
        out["intensification_index"]=(
            out["object_growth_pct_10min"].fillna(0)/100.0
            + out["reflectivity_change_db_10min"].fillna(0)/10.0
        )
    return out

def select_features(df: pd.DataFrame, include_optional: bool=False) -> list[str]:
    cols=[c for c in BASE_FEATURES if c in df.columns]
    if include_optional:
        cols += [c for c in df.columns if c.startswith("dualpol_") or c.startswith("mrms_")]
    return list(dict.fromkeys(cols))
