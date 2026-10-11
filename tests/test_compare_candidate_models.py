import json

from scripts.compare_candidate_models import load_metrics


def test_comparison_includes_grouped_calibration_metrics(tmp_path):
    model_dir = tmp_path / "baseline_expansion_15m"
    model_dir.mkdir()
    (model_dir / "metrics.json").write_text(json.dumps({
        "target": "squall_onset_within_15m",
        "evaluation_status": "case_held_out_exploratory",
        "training_rows": 120,
        "training_groups": 12,
        "metrics": {"brier_score": 0.18},
        "operational_release_status": "candidate_only",
    }))
    (model_dir / "calibration_report.json").write_text(json.dumps({
        "status": "research_only_not_independently_validated",
        "horizons": {
            "15": {
                "status": "fit_research_artifact",
                "cross_fitted_evaluation": {
                    "status": "evaluated_research_diagnostic_only",
                    "temporal_ordering_enforced": True,
                    "evaluated_rows": 40,
                    "raw_oof_probability_metrics": {
                        "brier_score": 0.20,
                        "log_loss": 0.62,
                        "expected_calibration_error_equal_frequency": 0.12,
                        "brier_skill_vs_fold_climatology": 0.10,
                    },
                    "cross_fitted_calibrated_probability_metrics": {
                        "brier_score": 0.16,
                        "log_loss": 0.51,
                        "expected_calibration_error_equal_frequency": 0.07,
                        "brier_skill_vs_fold_climatology": 0.28,
                    },
                },
            }
        },
    }))

    table = load_metrics(tmp_path)
    row = table.iloc[0]
    assert row["calibration_status"] == "fit_research_artifact"
    assert row["calibration_temporal_ordering_enforced"]
    assert row["raw_oof_brier_score"] == 0.20
    assert row["cross_fitted_calibrated_brier_score"] == 0.16
    assert row["cross_fitted_calibrated_ece"] == 0.07
    assert row["calibrated_brier_skill_vs_fold_climatology"] == 0.28
