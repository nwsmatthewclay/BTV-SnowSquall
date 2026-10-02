import json
from pathlib import Path

from scripts.audit_candidate_release import audit


HORIZONS = (15, 30, 45, 60)


def _make_bundle(root: Path, prefix: str, predictors: list[str]):
    for h in HORIZONS:
        bundle = root / f"{prefix}{h}m"
        bundle.mkdir(parents=True)
        (bundle / "baseline_model.joblib").write_bytes(b"placeholder")
        (bundle / "probability_calibrator.joblib").write_bytes(b"placeholder")
        (bundle / "metrics.json").write_text(
            json.dumps(
                {
                    "target": f"squall_onset_within_{h}m",
                    "predictor_columns": predictors,
                    "calibration_status": "fit_on_oof_research_data",
                    "calibration_method": "isotonic",
                    "operational_release_status": "candidate_only",
                }
            )
        )


def test_candidate_release_audit_requires_safe_candidate_structure(tmp_path):
    schema = {
        "future_information_policy": "current_and_past_only",
        "operational_predictor_columns": ["max_reflectivity_dbz"],
        "predictor_columns": ["max_reflectivity_dbz"],
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    root = tmp_path / "models"
    _make_bundle(root, "candidate_ensemble_expansion_", ["max_reflectivity_dbz"])

    report = audit(
        schema_path,
        root,
        "candidate_ensemble_expansion_",
    )
    assert report["status"] == "ready_for_human_review"
    assert report["automatic_release"] is False
    assert report["bundles_audited"] == 4
    assert report["common_predictor_count"] == 1


def test_candidate_release_audit_blocks_missing_calibration(tmp_path):
    schema = {
        "future_information_policy": "current_and_past_only",
        "operational_predictor_columns": ["max_reflectivity_dbz"],
        "predictor_columns": ["max_reflectivity_dbz"],
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    root = tmp_path / "models"
    _make_bundle(root, "candidate_ensemble_expansion_", ["max_reflectivity_dbz"])
    (root / "candidate_ensemble_expansion_30m" / "probability_calibrator.joblib").unlink()

    report = audit(
        schema_path,
        root,
        "candidate_ensemble_expansion_",
    )
    assert report["status"] == "blocked"
    assert "missing_calibrator_30m" in report["failures"]


def test_candidate_release_audit_can_attach_independent_validation(tmp_path):
    schema = {
        "future_information_policy": "current_and_past_only",
        "operational_predictor_columns": ["max_reflectivity_dbz"],
        "predictor_columns": ["max_reflectivity_dbz"],
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    root = tmp_path / "models"
    _make_bundle(root, "candidate_ensemble_expansion_", ["max_reflectivity_dbz"])

    validation = tmp_path / "validation"
    validation.mkdir()
    (validation / "validation_metrics.json").write_text(
        json.dumps({str(h): {"status": "unscored_no_observed_target"} for h in HORIZONS})
    )

    report = audit(
        schema_path,
        root,
        "candidate_ensemble_expansion_",
        validation,
    )
    assert report["status"] == "ready_for_human_review"
    assert report["independent_validation"] is not None
