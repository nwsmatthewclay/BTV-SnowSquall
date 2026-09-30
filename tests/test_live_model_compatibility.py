import json

import pytest

from scripts.audit_live_model_compatibility import audit_bundle


def _write_bundle(root, prefix, horizon, predictors):
    bundle = root / f"{prefix}{horizon}m"
    bundle.mkdir(parents=True)
    (bundle / "metrics.json").write_text(
        json.dumps({
            "target": f"squall_onset_within_{horizon}m",
            "predictor_columns": predictors,
            "operational_release_status": "candidate_only",
        }),
        encoding="utf-8",
    )


def test_live_model_compatibility_accepts_live_predictors(tmp_path):
    predictors = ["area_km2", "max_reflectivity_dbz", "shear_0_6km_kt"]
    schema = {"operational_predictor_columns": predictors}
    _write_bundle(tmp_path, "candidate_ensemble_expansion_", 15, predictors)

    result = audit_bundle(
        tmp_path,
        schema,
        "candidate_ensemble_expansion_",
        15,
    )

    assert result["status"] == "pass"
    assert result["predictor_count"] == 3


def test_live_model_compatibility_rejects_surface_predictor(tmp_path):
    predictors = ["area_km2", "visibility_m"]
    schema = {"operational_predictor_columns": predictors}
    _write_bundle(tmp_path, "candidate_ensemble_expansion_", 15, predictors)

    with pytest.raises(ValueError, match="non-live predictors"):
        audit_bundle(
            tmp_path,
            schema,
            "candidate_ensemble_expansion_",
            15,
        )


def test_candidate_bundle_is_explicitly_non_operational(tmp_path):
    predictors = ["area_km2", "max_reflectivity_dbz"]
    schema = {"operational_predictor_columns": predictors}
    _write_bundle(tmp_path, "candidate_ensemble_expansion_", 30, predictors)

    result = audit_bundle(
        tmp_path,
        schema,
        "candidate_ensemble_expansion_",
        30,
    )

    assert result["status"] == "pass"
    assert result["operational_release_status"] == "candidate_only"


def test_live_bundle_horizon_contract_is_exact(tmp_path):
    predictors = ["area_km2", "max_reflectivity_dbz"]
    schema = {"operational_predictor_columns": predictors}
    _write_bundle(tmp_path, "candidate_ensemble_expansion_", 45, predictors)

    result = audit_bundle(
        tmp_path,
        schema,
        "candidate_ensemble_expansion_",
        45,
    )

    assert result["target"] == "squall_onset_within_45m"
