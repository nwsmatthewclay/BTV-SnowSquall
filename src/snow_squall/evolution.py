"""Shared causal storm/environment evolution feature generation.

The same routine is used by historical feature construction and the live model
adapter so predictor semantics cannot drift between training and inference.
"""
from __future__ import annotations

from typing import Iterable

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
    dt_min = (times - group[time_col].shift(1)).dt.total_seconds() / 60.0
    continuity = dt_min.between(0, max_gap_minutes, inclusive="both")

    previous_dt_min = (
        group[time_col].shift(1) - group[time_col].shift(2)
    ).dt.total_seconds() / 60.0
    second_dt_min = (
        times - group[time_col].shift(2)
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
