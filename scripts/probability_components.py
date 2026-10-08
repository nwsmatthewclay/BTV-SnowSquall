"""Transparent 0-100 Snow Squall component scoring for live/research guidance.

This module deliberately separates three component scores from the final weighted
probability. Each component is always expressed on a 0-100 scale:

    radar        50%
    environment  50%
    analog       0%

The resulting weighted value is still 0-100. These are research guidance
scores, not calibrated operational probabilities.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping


WEIGHTS = {"radar": 0.50, "environment": 0.50, "analog": 0.00}
HORIZONS = (15, 30, 45, 60)


def _num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))


def _scale(value, low, high):
    value = _num(value)
    if value is None or high <= low:
        return None
    return _clamp((value - low) / (high - low))


def _mean_available(values, default=0.0):
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return sum(vals) / len(vals) if vals else default


def radar_component(record: Mapping) -> tuple[float, dict]:
    """Return a transparent radar-signature score on 0-100.

    The ingredients emphasize coherent low-level snow-squall structure:
    reflectivity intensity/contrast, leading-edge gradient, velocity contrast,
    object organization, and recent evolution.
    """
    max_z = _scale(record.get("max_reflectivity_dbz"), 20.0, 45.0)
    contrast = _scale(record.get("reflectivity_contrast_db"), 3.0, 12.0)
    gradient = _scale(record.get("reflectivity_gradient_p90_dbkm"), 2.0, 8.0)
    velocity = _scale(record.get("velocity_contrast_kt"), 5.0, 25.0)
    core = _scale(record.get("core_fraction"), 0.08, 0.45)
    growth = _scale(record.get("reflectivity_trend_dbz_per_hr"), -5.0, 15.0)

    # A modest organization bonus for elongated/trackable objects.
    aspect = _scale(record.get("aspect_ratio"), 1.0, 4.0)
    age = _scale(record.get("track_age_scans"), 1.0, 5.0)

    ingredients = {
        "reflectivity": max_z,
        "reflectivity_contrast": contrast,
        "leading_edge_gradient": gradient,
        "velocity_contrast": velocity,
        "core_fraction": core,
        "reflectivity_growth": growth,
        "organization": _mean_available([aspect, age], default=0.0),
    }
    weights = {
        "reflectivity": 0.27,
        "reflectivity_contrast": 0.16,
        "leading_edge_gradient": 0.16,
        "velocity_contrast": 0.16,
        "core_fraction": 0.08,
        "reflectivity_growth": 0.10,
        "organization": 0.07,
    }

    # Missing radar moments do not force the score to zero. Renormalize over
    # available ingredients so partial dual-pol/velocity coverage remains useful.
    numerator = sum(weights[k] * v for k, v in ingredients.items() if v is not None)
    denominator = sum(weights[k] for k, v in ingredients.items() if v is not None)
    score = 100.0 * (numerator / denominator if denominator else 0.0)
    return round(score, 2), ingredients


def environment_component(record: Mapping) -> tuple[float, dict]:
    """Return the existing literature-informed environment index on 0-100."""
    env = record.get("environment") if isinstance(record.get("environment"), Mapping) else {}
    fields = dict(env.get("fields") or {})
    fields.update({k: v for k, v in record.items() if k not in fields})

    # environment_risk_features is already part of the repository's common
    # environment contract. Import lazily so this module stays lightweight.
    from snow_squall.environment_risk import environment_risk_features

    risk = environment_risk_features(fields)
    base = _num(risk.get("snow_squall_environment_score"))
    if base is None:
        return 50.0, {"status": "unavailable", "source": "RAP", "coverage": 0.0}

    current = 100.0 * _clamp(base)

    # Snow squalls require a plausible snow-at-surface environment. Prevent
    # CAPE/RH/shear from producing a high score when the existing RAP/MetPy
    # snow-temperature gate says the profile cannot support snow at the surface.
    snow_pass = record.get("snow_temperature_pass")
    wetbulb = _num(record.get("wetbulb_2m_c"))
    freezing_level = _num(record.get("freezing_level_m"))
    if snow_pass is False:
        current *= 0.15
    elif snow_pass is None and wetbulb is not None and wetbulb > 3.0:
        current *= 0.25
    if freezing_level is not None and freezing_level > 1800.0:
        current *= 0.70

    forecast = record.get("environment_forecast_30min")
    forecast_fields = forecast.get("fields") if isinstance(forecast, Mapping) else None
    forecast_score = None
    if isinstance(forecast_fields, Mapping):
        forecast_risk = environment_risk_features(forecast_fields)
        fr = _num(forecast_risk.get("snow_squall_environment_score"))
        if fr is not None:
            forecast_score = 100.0 * _clamp(fr)
            if forecast_fields.get("snow_temperature_pass") is False:
                forecast_score *= 0.15
            elif forecast_fields.get("snow_temperature_pass") is None and _num(forecast_fields.get("wetbulb_2m_c")) is not None and _num(forecast_fields.get("wetbulb_2m_c")) > 3.0:
                forecast_score *= 0.25
            forecast_freezing = _num(forecast_fields.get("freezing_level_m"))
            if forecast_freezing is not None and forecast_freezing > 1800.0:
                forecast_score *= 0.70

    # Current environment is primary. A valid +30 RAP forecast contributes
    # increasingly to the longer horizons; 45/60 extrapolate cautiously from
    # the +30 guidance rather than pretending we have a +60 RAP analysis.
    return round(current, 2), {
        "current": round(current, 2),
        "forecast_30": round(forecast_score, 2) if forecast_score is not None else None,
        "coverage": round(sum(risk.get(f"{key}_risk") is not None for key in ("cape_jkg", "mean_rh_0_2km_pct", "thetae_delta_0_2km_k", "mean_wind_0_2km_ms", "lapse_rate_0_3km_c_km", "snsq")) / 6.0, 3),
    }


def _load_analog_cases():
    candidates = (
        Path("data/derived/analog_cases.jsonl"),
        Path("data/derived/analog_case_catalog.jsonl"),
        Path("data/derived/analog_cases.json"),
        Path("data/derived/analog_case_catalog.json"),
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix == ".jsonl":
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = payload if isinstance(payload, list) else payload.get("cases", [])
            if rows:
                return rows, str(path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return [], None


def analog_component(record: Mapping) -> tuple[float, dict]:
    """Preliminary analog score.

    If a labeled analog catalog exists, use nearest standardized feature
    similarity. Until that catalog is populated, return a neutral 50 rather
    than manufacture a probability from unlabeled history.
    """
    cases, source = _load_analog_cases()
    if not cases:
        return 50.0, {
            "status": "provisional_neutral",
            "source": None,
            "message": "Analog catalog not yet populated; 15% component held neutral.",
            "matches": 0,
        }

    features = (
        ("max_reflectivity_dbz", 20.0),
        ("reflectivity_contrast_db", 5.0),
        ("reflectivity_gradient_p90_dbkm", 4.0),
        ("velocity_contrast_kt", 10.0),
        ("area_km2", 25.0),
        ("motion_speed_kt", 20.0),
        ("snsq", 0.75),
        ("cape_jkg", 50.0),
        ("mean_rh_0_2km_pct", 70.0),
        ("mean_wind_0_2km_ms", 10.0),
        ("lapse_rate_0_3km_c_km", 6.5),
    )

    distances = []
    for case in cases:
        total = 0.0
        used = 0
        for key, scale in features:
            a = _num(record.get(key))
            b = _num(case.get(key))
            if a is None or b is None:
                continue
            total += ((a - b) / scale) ** 2
            used += 1
        if used < 4:
            continue
        label = case.get("outcome_probability")
        if label is None:
            label = case.get("outcome")
        label = _num(label)
        if label is not None:
            if label > 1.0:
                label /= 100.0
            distances.append((math.sqrt(total / used), _clamp(label)))

    if not distances:
        return 50.0, {
            "status": "catalog_unlabeled",
            "source": source,
            "message": "Analog cases exist but lack labeled outcomes; held neutral.",
            "matches": 0,
        }

    distances.sort(key=lambda x: x[0])
    nearest = distances[: min(8, len(distances))]
    # Distance-weighted nearest-neighbor estimate, converted to 0-100.
    weights = [1.0 / max(d, 0.05) for d, _ in nearest]
    estimate = sum(w * y for w, (_, y) in zip(weights, nearest)) / sum(weights)
    return round(100.0 * estimate, 2), {
        "status": "experimental",
        "source": source,
        "matches": len(nearest),
        "nearest_distance": round(nearest[0][0], 3),
    }


def horizon_component_scores(record: Mapping) -> dict:
    radar, radar_detail = radar_component(record)
    env, env_detail = environment_component(record)
    # Analogs are retained only as an optional diagnostic for future research;
    # they have zero weight in the snow-squall probability equation.
    # Analog matching is diagnostic research only and is deliberately excluded\n    # from all Snow Squall probabilities. Keep it available for research audits.\n    analog, analog_detail = analog_component(record)

    radar_growth = _num(record.get("reflectivity_trend_dbz_per_hr"))
    radar_horizon = {}
    env_horizon = {}
    analog_horizon = {}

    for horizon in HORIZONS:
        # Project the radar component using observed intensity trend. This is
        # deliberately modest: no trend can move the score by more than 20
        # points through the 60-minute horizon.
        trend_adjustment = 0.0 if radar_growth is None else _clamp((radar_growth + 5.0) / 20.0) - 0.25
        radar_h = _clamp((radar + trend_adjustment * horizon * 0.45) / 100.0) * 100.0
        radar_horizon[horizon] = round(radar_h, 2)

        if horizon <= 15:
            env_h = env
        elif horizon == 30:
            f = env_detail.get("forecast_30")
            env_h = env if f is None else 0.60 * env + 0.40 * f
        elif horizon == 45:
            f = env_detail.get("forecast_30")
            env_h = env if f is None else 0.40 * env + 0.60 * f
        else:
            f = env_detail.get("forecast_30")
            env_h = env if f is None else 0.25 * env + 0.75 * f
        env_horizon[horizon] = round(_clamp(env_h / 100.0) * 100.0, 2)
        analog_horizon[horizon] = 50.0

    final = {}
    components = {}
    for horizon in HORIZONS:
        rs = radar_horizon[horizon]
        es = env_horizon[horizon]
        final[horizon] = round(rs * WEIGHTS["radar"] + es * WEIGHTS["environment"], 2)
        components[horizon] = {
            "radar": rs,
            "environment": es,
            "analog": 0.0,
            "weights": dict(WEIGHTS),
        }

    return {
        "probabilities": final,
        "components": components,
        "radar": {"score": radar, "detail": radar_detail},
        "environment": {"score": env, "detail": env_detail},
        "analog": {"score": 50.0, "detail": {"status": "provisional_neutral", "message": "Analog cases are diagnostic only and excluded from the probability equation."}},
        "status": "research_weighted_components",
    }
