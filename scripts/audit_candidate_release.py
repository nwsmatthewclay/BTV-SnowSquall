"""Audit a candidate model package for safe human review.

This is a release-packaging gate, not a performance ranking. It verifies
feature-policy integrity, calibrated bundles, and explicit candidate-only
status. Independent verification remains a separate input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.audit_live_model_compatibility import HORIZONS, audit_bundle


def audit(
    schema_path: Path,
    model_root: Path,
    prefix: str,
    validation_root: Path | None = None,
) -> dict:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    warnings: list[str] = []

    if schema.get("future_information_policy") != "current_and_past_only":
        failures.append(
            "schema_future_information_policy_not_current_and_past_only"
        )

    rows = []
    predictor_sets = []
    for horizon in HORIZONS:
        bundle = model_root / f"{prefix}{horizon}m"
        metrics_path = bundle / "metrics.json"
        model_path = bundle / "baseline_model.joblib"
        calibrator_path = bundle / "probability_calibrator.joblib"

        if not metrics_path.exists():
            failures.append(f"missing_metrics_{horizon}m")
            continue
        if not model_path.exists():
            failures.append(f"missing_model_{horizon}m")
            continue
        if not calibrator_path.exists():
            failures.append(f"missing_calibrator_{horizon}m")
            continue

        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        predictor_sets.append(
            tuple(metrics.get("predictor_columns") or [])
        )

        if metrics.get("calibration_status") != "fit_on_oof_research_data":
            failures.append(f"missing_oof_calibration_status_{horizon}m")

        status = metrics.get("operational_release_status")
        if status not in {
            "candidate_only",
            "candidate_only_not_operational",
        }:
            failures.append(
                f"unexpected_release_status_{horizon}m:{status!r}"
            )

        target = str(metrics.get("target") or "")
        expected_target = f"squall_onset_within_{horizon}m"
        if target != expected_target:
            failures.append(
                f"target_mismatch_{horizon}m:{target!r}"
            )

        try:
            compatibility = audit_bundle(
                model_root,
                schema,
                prefix,
                horizon,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            failures.append(
                f"compatibility_failure_{horizon}m:{type(exc).__name__}:{exc}"
            )
            compatibility = {
                "status": "fail",
                "bundle": bundle.name,
                "horizon_minutes": horizon,
            }

        rows.append(
            {
                **compatibility,
                "calibration_status": metrics.get("calibration_status"),
                "calibration_method": metrics.get("calibration_method"),
                "operational_release_status": status,
            }
        )

    if predictor_sets and len(set(predictor_sets)) != 1:
        failures.append("predictor_contract_differs_across_horizons")

    validation_summary = None
    if validation_root is None:
        warnings.append("independent_validation_not_supplied")
    else:
        metrics_path = validation_root / "validation_metrics.json"
        if not metrics_path.exists():
            failures.append("independent_validation_metrics_missing")
        else:
            validation_summary = json.loads(
                metrics_path.read_text(encoding="utf-8")
            )
            for horizon in HORIZONS:
                item = validation_summary.get(str(horizon), {})
                if not item:
                    warnings.append(
                        f"independent_validation_horizon_missing_{horizon}m"
                    )

    status = "blocked" if failures else "ready_for_human_review"

    return {
        "status": status,
        "automatic_release": False,
        "operational_release_status": "candidate_only_not_operational",
        "release_policy": (
            "Candidate bundles remain non-operational until independent "
            "verification and an explicit human release decision."
        ),
        "future_information_policy": schema.get(
            "future_information_policy"
        ),
        "bundle_prefix": prefix,
        "bundles_audited": len(rows),
        "common_predictor_count": (
            len(predictor_sets[0]) if predictor_sets else 0
        ),
        "bundles": rows,
        "independent_validation": validation_summary,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", type=Path, required=True)
    ap.add_argument("--model-root", type=Path, required=True)
    ap.add_argument("--prefix", default="candidate_ensemble_expansion_")
    ap.add_argument("--validation-root", type=Path, default=None)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    report = audit(
        args.schema,
        args.model_root,
        args.prefix,
        args.validation_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))

    if report["status"] == "blocked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
