"""Run the cross-path beta readiness contract for the snow-squall model foundation.

This is a deterministic CI gate. It checks that the historical/live feature
interfaces agree on the operational predictor vocabulary, the live adapter
preserves unit-safe derived fields, candidate scoring remains non-operational,
and the training viewer keeps the research-only contract.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from scripts.build_model_features import OPERATIONAL_LIVE_PREDICTORS, build_features, predictor_columns
from scripts.live_model_features import build_live_feature_frame, feature_coverage
from scripts.shadow_live_model_scorer import MIN_FEATURE_COVERAGE


ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (15, 30, 45, 60)


def _finite_tree(value):
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite_tree(v) for v in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _synthetic_history() -> list[dict]:
    base = {
        "scan_time_utc": "2026-01-01T00:00:00Z",
        "timestamp": "2026-01-01T00:00:00Z",
        "track_id": "beta-track-1",
        "object_id": "beta-object-1",
        "radar_site": "KCXX",
        "centroid_lat": 44.5,
        "centroid_lon": -73.2,
        "area_km2": 100.0,
        "length_km": 20.0,
        "width_km": 8.0,
        "aspect_ratio": 2.5,
        "motion_dir_deg": 270.0,
        "motion_speed_kt": 30.0,
        "max_reflectivity_dbz": 45.0,
        "mean_reflectivity_dbz": 30.0,
        "core_pixel_count": 100.0,
        "pixel_count": 400.0,
        "core_fraction": 0.25,
        "age_scans": 1,
        "echo_top_km": 4.0,
        "top_minus_base_km": 3.5,
        "vertical_reflectivity_gradient": 2.0,
        "vertical_valid_points": 10.0,
        "zdr_mean_db": 0.5,
        "zdr_p90_db": 1.0,
        "zdr_gradient_dbkm": 0.1,
        "rhohv_mean": 0.97,
        "rhohv_max": 0.99,
        "rhohv_p90": 0.98,
        "rhohv_min": 0.90,
        "kdp_mean_degkm": 0.2,
        "kdp_p90_degkm": 0.4,
        "velocity_mean_kt": 20.0,
        "velocity_std_kt": 5.0,
        "velocity_p90_abs_kt": 30.0,
        "velocity_gradient_ktkm": 1.0,
        "snsq": 1.0,
        "mean_rh_0_2km_pct": 85.0,
        "thetae_delta_0_2km_k": -2.0,
        "mean_wind_0_2km_ms": 12.0,
        "wetbulb_2m_c": 0.0,
        "snsq_moisture_factor": 1.0,
        "snsq_instability_factor": 1.0,
        "snsq_wind_factor": 1.0,
        "frontogenesis": 1.0,
        "dcva": 1.0,
        "omega": -0.5,
        "epv": 0.1,
        "cloud_layer_depth_m": 3000.0,
        "cloud_layer_rh_pct": 90.0,
        "cloud_layer_mean_wind_kt": 25.0,
        "cloud_layer_shear_kt": 10.0,
        "mlcape_jkg": 50.0,
        "mlcin_jkg": -10.0,
        "mucape_jkg": 100.0,
        "mucin_jkg": -20.0,
        "pwat_mm": 8.0,
        "srh01_m2s2": 25.0,
        "srh03_m2s2": 50.0,
        "shear_u_0_6km_ms": 10.0,
        "shear_v_0_6km_ms": 5.0,
        "shear_0_6km_ms": 11.18,
        "u10_ms": 8.0,
        "v10_ms": 6.0,
        "temperature_2m_k": 273.15,
        "dewpoint_2m_k": 271.15,
        "rh_2m_pct": 90.0,
        "gust_ms": 15.0,
        "visibility_m": 1609.344,
        "cape_jkg": 50.0,
        "cin_jkg": -25.0,
    }
    newer = dict(base)
    newer["scan_time_utc"] = "2026-01-01T00:06:00Z"
    newer["timestamp"] = "2026-01-01T00:06:00Z"
    newer["centroid_lon"] = -73.15
    newer["max_reflectivity_dbz"] = 47.0
    newer["area_km2"] = 110.0
    newer["age_scans"] = 2
    latest = dict(newer)
    latest["scan_time_utc"] = "2026-01-01T00:12:00Z"
    latest["timestamp"] = "2026-01-01T00:12:00Z"
    latest["centroid_lon"] = -73.10
    latest["max_reflectivity_dbz"] = 49.0
    latest["area_km2"] = 120.0
    latest["age_scans"] = 3
    return [base, newer, latest]


def main() -> None:
    failures: list[str] = []
    history = _synthetic_history()

    # 1) Historical and live schemas must expose the same operational vocabulary.
    hist_frame = pd.DataFrame(history)
    hist_features = build_features(hist_frame)
    hist_predictors = set(predictor_columns(hist_features))
    live_features = build_live_feature_frame(history, "beta-track-1")
    live_missing = sorted(OPERATIONAL_LIVE_PREDICTORS - set(live_features.columns))
    historical_missing = sorted(OPERATIONAL_LIVE_PREDICTORS - hist_predictors)
    if live_missing:
        failures.append("live adapter missing operational predictors: " + ", ".join(live_missing))
    if historical_missing:
        failures.append("historical builder missing operational predictors: " + ", ".join(historical_missing))

    # 2) Live/historical derived-unit contracts.
    latest = live_features.iloc[-1].to_dict()
    expected_surface_wind = math.hypot(8.0, 6.0) * 1.943844492
    if abs(float(latest["surface_wind_speed_kt"]) - expected_surface_wind) > 1e-9:
        failures.append("surface_wind_speed_kt conversion contract failed")
    expected_gust = 15.0 * 1.943844492
    if abs(float(latest["wind_gust_kt"]) - expected_gust) > 1e-9:
        failures.append("wind_gust_kt conversion contract failed")
    expected_shear = math.hypot(10.0, 5.0) * 1.943844492
    if abs(float(latest["shear_0_6km_kt"]) - expected_shear) > 1e-9:
        failures.append("shear_0_6km_kt conversion contract failed")
    if float(latest["visibility_sm"]) <= 0:
        failures.append("visibility_sm conversion contract failed")
    if float(latest["centroid_displacement_km"]) <= 0:
        failures.append("haversine motion derivation missing")

    # 3) Shadow scorer must remain a guarded research path.
    if MIN_FEATURE_COVERAGE < 0.80:
        failures.append("live shadow feature coverage gate is below 0.80")
    shadow_src = (ROOT / "scripts/shadow_live_model_scorer.py").read_text(encoding="utf-8")
    if "candidate_only_not_operational" not in shadow_src:
        failures.append("live shadow path lacks candidate-only release status")
    if "monotone_cumulative_probabilities" not in shadow_src:
        failures.append("live shadow path lacks cumulative horizon post-processing")

    # 4) Training viewer must remain explicitly research-only.
    training_html = ROOT / "viewer/training.html"
    viewer_js = ROOT / "viewer/app.js"
    if not training_html.exists():
        failures.append("training viewer shell missing")
    else:
        html = training_html.read_text(encoding="utf-8")
        for token in ('data-mode="training"', "probabilityEvolutionBody", "research", "BTV"):
            if token not in html:
                failures.append("training viewer missing contract token: " + token)
    if not viewer_js.exists():
        failures.append("shared viewer JavaScript missing")
    else:
        js = viewer_js.read_text(encoding="utf-8")
        for token in ("renderProbabilityEvolution", "activePointIndex", "Current scan:", "candidate_only_not_operational"):
            if token not in js:
                failures.append("viewer JS missing beta contract token: " + token)

    # 5) Strict JSON helper contract: persisted live payloads must be serializable.
    strict_probe = {
        "finite": [1.0, 2.0, {"x": 3.0}],
        "none": None,
    }
    if not _finite_tree(strict_probe):
        failures.append("finite JSON probe unexpectedly failed")
    if _finite_tree({"bad": float("nan")}):
        failures.append("non-finite JSON values were not rejected")

    # 6) Future-information policy must remain explicit in core model artifacts.
    feature_src = (ROOT / "scripts/build_model_features.py").read_text(encoding="utf-8")
    if "current_and_past_only" not in feature_src:
        failures.append("historical feature builder lacks explicit future-information policy")

    coverage = feature_coverage(live_features.tail(1), sorted(OPERATIONAL_LIVE_PREDICTORS))
    summary = {
        "status": "pass" if not failures else "fail",
        "operational_predictor_count": len(OPERATIONAL_LIVE_PREDICTORS),
        "historical_predictors": len(hist_predictors),
        "live_columns": len(live_features.columns),
        "operational_live_coverage": coverage["fraction"],
        "shadow_min_feature_coverage": MIN_FEATURE_COVERAGE,
        "viewer_research_only": True,
        "horizons_minutes": list(HORIZONS),
        "failures": failures,
    }
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
