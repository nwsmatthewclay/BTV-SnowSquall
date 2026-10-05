import pandas as pd

from scripts.model_scoring_contract import (
    MIN_FEATURE_COVERAGE,
    assess_model_input_readiness,
)


def _frame(complete=True):
    base = {
        "max_reflectivity_dbz": 35.0,
        "mean_reflectivity_dbz": 25.0,
        "area_km2": 20.0,
        "length_km": 8.0,
        "width_km": 3.0,
        "core_pixel_count": 20.0,
        "bbox_aspect_ratio": 2.5,
        "reflectivity_gradient_p90_dbkm": 7.0,
        "gradient_fraction_above_5dbkm": 0.2,
        "background_reflectivity_dbz": 18.0,
        "reflectivity_contrast_db": 6.0,
        "cape_jkg": 25.0,
    }
    if not complete:
        base.pop("reflectivity_contrast_db")
    return pd.DataFrame([base])


def _env_ready():
    return {"ready": True, "reasons": []}


def test_complete_inputs_pass_shared_gate():
    frame = _frame()
    result = assess_model_input_readiness(
        frame,
        ["max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2", "cape_jkg"],
        _env_ready(),
    )
    assert result["ready"]
    assert result["feature_coverage"]["fraction"] == 1.0
    assert result["instantaneous_feature_count"] == 11


def test_low_coverage_is_blocked():
    frame = _frame()
    result = assess_model_input_readiness(
        frame,
        [
            "max_reflectivity_dbz",
            "mean_reflectivity_dbz",
            "area_km2",
            "cape_jkg",
            "missing_a",
            "missing_b",
            "missing_c",
            "missing_d",
            "missing_e",
        ],
        _env_ready(),
    )
    assert result["feature_coverage"]["fraction"] < MIN_FEATURE_COVERAGE
    assert not result["ready"]
    assert any(reason.startswith("low_feature_coverage:") for reason in result["reasons"])


def test_incomplete_environment_is_blocked_even_with_good_features():
    result = assess_model_input_readiness(
        _frame(),
        ["max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2", "cape_jkg"],
        {"ready": False, "reasons": ["stale:120.0"]},
    )
    assert not result["ready"]
    assert "environment_not_model_ready:stale:120.0" in result["reasons"]


def test_insufficient_instantaneous_features_is_explicit():
    result = assess_model_input_readiness(
        _frame(complete=False),
        ["max_reflectivity_dbz", "mean_reflectivity_dbz", "area_km2", "cape_jkg"],
        _env_ready(),
        min_instantaneous_features=11,
    )
    assert not result["ready"]
    assert "insufficient_instantaneous_object_features:10/11" in result["reasons"]
