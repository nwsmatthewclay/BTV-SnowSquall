"""Shared model-input readiness contract for live and historical research scoring.

The same feature-coverage and instantaneous radar-structure gate is used by
live shadow scoring and chronological historical replay. This prevents a
historical replay from scoring objects that the live research path would
reject.
"""
from __future__ import annotations

import math
from typing import Mapping

import pandas as pd

from scripts.live_model_features import feature_coverage

MIN_FEATURE_COVERAGE = 0.80

# These are intentionally causal, instantaneous object/radar measurements.
# They must be present on the current scan before a model score can be emitted.
MIN_INSTANTANEOUS_FEATURES = frozenset(
    {
        "max_reflectivity_dbz",
        "mean_reflectivity_dbz",
        "area_km2",
        "length_km",
        "width_km",
        "core_pixel_count",
        "bbox_aspect_ratio",
        "reflectivity_gradient_p90_dbkm",
        "gradient_fraction_above_5dbkm",
        "background_reflectivity_dbz",
        "reflectivity_contrast_db",
    }
)
MIN_INSTANTANEOUS_FEATURE_COUNT = 6


def assess_model_input_readiness(
    frame: pd.DataFrame,
    feature_columns: list[str] | tuple[str, ...],
    environment_readiness: Mapping[str, object] | None,
    *,
    min_feature_coverage: float = MIN_FEATURE_COVERAGE,
    min_instantaneous_features: int = MIN_INSTANTANEOUS_FEATURE_COUNT,
) -> dict:
    """Return a deterministic gate report for one model-scoring timestep."""
    current = frame.tail(1) if not frame.empty else frame
    coverage = feature_coverage(current, list(feature_columns))
    available = [
        column
        for column in MIN_INSTANTANEOUS_FEATURES
        if column in current.columns and current[column].notna().any()
    ]
    reasons: list[str] = []

    fraction = float(coverage.get("fraction", 0.0))
    if not math.isfinite(fraction) or fraction < min_feature_coverage:
        reasons.append(f"low_feature_coverage:{fraction:.3f}")

    if len(available) < min_instantaneous_features:
        reasons.append(
            "insufficient_instantaneous_object_features:"
            f"{len(available)}/{min_instantaneous_features}"
        )

    env = dict(environment_readiness or {})
    if not bool(env.get("ready")):
        env_reasons = env.get("reasons") or ["environment_not_model_ready"]
        reasons.append(
            "environment_not_model_ready:" + ",".join(str(x) for x in env_reasons)
        )

    return {
        "ready": not reasons,
        "feature_coverage": coverage,
        "available_instantaneous_features": available,
        "instantaneous_feature_count": len(available),
        "minimum_feature_coverage": float(min_feature_coverage),
        "minimum_instantaneous_features": int(min_instantaneous_features),
        "environment_ready": bool(env.get("ready")),
        "reasons": reasons,
    }
