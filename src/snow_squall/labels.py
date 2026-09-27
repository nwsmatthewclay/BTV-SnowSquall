"""Construct leakage-controlled lead-time targets."""
from __future__ import annotations
import pandas as pd

def add_lead_time_target(
    df: pd.DataFrame,
    onset_col: str = "truth_onset_time",
    scan_col: str = "scan_time",
    horizon_minutes: int = 30,
) -> pd.DataFrame:
    out=df.copy()
    out[scan_col]=pd.to_datetime(out[scan_col], utc=True)
    out[onset_col]=pd.to_datetime(out[onset_col], utc=True, errors="coerce")
    delta=(out[onset_col]-out[scan_col]).dt.total_seconds()/60.0
    out["lead_time_min"]=delta
    out["snow_squall_30min"]=(
        out[onset_col].notna() & delta.ge(0) & delta.le(horizon_minutes)
    ).astype("int8")
    return out

def exclude_leakage_columns(columns: list[str]) -> list[str]:
    forbidden={"truth_onset_time","truth_end_time","sqw_intersection","manual_label","label_confidence","label_source","lead_time_min","snow_squall_30min"}
    return [c for c in columns if c not in forbidden]
