"""Literature-informed snow-squall environmental risk scoring.

These thresholds are intentionally diagnostic, not probability calibrations.
They are anchored to Banacos et al. (2014), NWS snow-squall guidance, and
regional snow-squall climatology. The ML model remains responsible for learning
the relationship between these ingredients and verified outcomes.
"""
from __future__ import annotations

from typing import Mapping


# (yellow threshold, red threshold, direction)
# direction="high" means larger values are more supportive;
# direction="low" means smaller values are more supportive.
RISK_THRESHOLDS = {
    "cape_jkg": (10.0, 50.0, "high"),
    "mean_rh_0_2km_pct": (60.0, 75.0, "high"),
    "thetae_delta_0_2km_k": (4.0, 0.0, "low"),
    # Banacos 2014: event IQR ~17.5-25.5 kt; median 22.5 kt.
    "mean_wind_0_2km_ms": (9.0, 13.1, "high"),
    # Literature describes steep low-level lapse rates; 6-7 C/km is
    # deliberately conservative rather than treating this as a hard cutoff.
    "lapse_rate_0_3km_c_km": (6.0, 7.0, "high"),
    "snsq": (0.5, 1.0, "high"),
}


def _num(value):
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None


def risk_fraction(value, key: str):
    value = _num(value)
    spec = RISK_THRESHOLDS.get(key)
    if value is None or spec is None:
        return None
    yellow, red, direction = spec
    if direction == "high":
        if value <= yellow:
            return 0.0
        if value >= red:
            return 1.0
        return (value - yellow) / (red - yellow)
    # Low values are more supportive (theta-e decreasing with height).
    if value >= yellow:
        return 0.0
    if value <= red:
        return 1.0
    return (yellow - value) / (yellow - red)


def risk_class(value, key: str) -> str:
    score = risk_fraction(value, key)
    if score is None:
        return "na"
    if score >= 1.0:
        return "red"
    if score > 0.0:
        return "yellow"
    return "green"


def environment_risk_features(record: Mapping) -> dict:
    """Return explainable component scores plus a simple aggregate index."""
    scores = {}
    classes = {}
    for key in RISK_THRESHOLDS:
        score = risk_fraction(record.get(key), key)
        scores[f"{key}_risk"] = score
        classes[f"{key}_risk_class"] = risk_class(record.get(key), key)

    finite = [v for k, v in scores.items() if k.endswith("_risk") and v is not None]
    # Equal-weight ingredients index. This is a feature, not an operational
    # probability; the supervised model must learn the outcome relationship.
    aggregate = sum(finite) / len(finite) if finite else None
    high_count = sum(1 for v in finite if v >= 1.0)

    scores["snow_squall_environment_score"] = aggregate
    scores["snow_squall_environment_high_risk_count"] = float(high_count)
    scores.update(classes)
    return scores
