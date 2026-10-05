"""Determine whether a learned Snow Squall candidate is ready for research-operational shadow use.

This is deliberately NOT an operational release switch. It creates an explicit
staging status from candidate bundle integrity, calibration, leakage-safe
case-held-out evidence, and minimum positive-case support.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HORIZONS = (15, 30, 45, 60)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(model_root: Path, audit_path: Path, gate_path: Path, summary_path: Path | None = None) -> dict:
    audit = load_json(audit_path)
    gate = load_json(gate_path)
    summary = load_json(summary_path) if summary_path and summary_path.exists() else {}
    candidate_mode = str(summary.get("candidate_mode") or "strict_refresh")
    bootstrap_mode = candidate_mode.startswith("bootstrap")

    horizon = {}
    all_bundle_ok = True
    all_calibrated = True
    minimum_support_ok = True
    skill_evidence = 0

    for h in HORIZONS:
        bundle = model_root / f"candidate_ensemble_refresh_{h}m"
        metrics_path = bundle / "metrics.json"
        if not metrics_path.exists():
            all_bundle_ok = False
            horizon[str(h)] = {"status": "missing_bundle"}
            continue

        metrics = load_json(metrics_path)
        calibrated = metrics.get("calibration_status") == "fit_on_oof_research_data"
        positive_groups = int(metrics.get("positive_case_group_count") or 0)
        eval_status = str(metrics.get("evaluation_status") or "")
        nested = metrics.get("metrics") or {}
        climatology = nested.get("climatology") or {}
        candidate_brier = nested.get("brier_score")
        climate_brier = climatology.get("brier_score")
        beats_climatology = (
            candidate_brier is not None
            and climate_brier is not None
            and float(candidate_brier) < float(climate_brier)
        )

        all_calibrated &= calibrated
        minimum_support_ok &= positive_groups >= 3
        skill_evidence += int(beats_climatology)

        horizon[str(h)] = {
            "bundle_present": True,
            "calibrated": calibrated,
            "positive_case_groups": positive_groups,
            "evaluation_status": eval_status,
            "brier_score": candidate_brier,
            "climatology_brier_score": climate_brier,
            "brier_beats_climatology": beats_climatology,
            "operational_release_status": metrics.get("operational_release_status"),
        }

    gate_ok_horizons = [
        h for h in HORIZONS
        if str(h) in gate
        and gate[str(h)].get("status") == "ok"
    ]

    if (not bootstrap_mode and all_bundle_ok and all_calibrated and minimum_support_ok
            and len(gate_ok_horizons) >= 3 and skill_evidence >= 2):
        status = "research_operational_candidate"
    elif all_bundle_ok and all_calibrated:
        status = "limited_data_candidate"
    else:
        status = "candidate_incomplete"

    return {
        "schema_version": "research-operational-candidate-v1",
        "status": status,
        "probability_enablement": False,
        "live_shadow_enablement": all_bundle_ok and all_calibrated,
        "operational_release_status": "candidate_only_not_operational",
        "candidate_mode": candidate_mode,
        "bootstrap_mode": bootstrap_mode,
        "minimum_positive_case_groups_per_horizon": 3,
        "minimum_gate_horizons": 3,
        "minimum_horizons_beating_climatology_brier": 2,
        "horizons_with_case_heldout_evidence": gate_ok_horizons,
        "horizons_beating_climatology_brier": skill_evidence,
        "candidate_bundle_integrity": all_bundle_ok,
        "candidate_calibration_complete": all_calibrated,
        "minimum_positive_case_support_complete": minimum_support_ok,
        "candidate_release_audit_status": audit.get("status"),
        "case_heldout_gate_status": {
            str(h): gate.get(str(h), {}).get("status") for h in HORIZONS
        },
        "horizons": horizon,
        "release_note": (
            "This package is permitted for live research-shadow scoring only. "
            "Independent modern validation, sustained live verification, and "
            "human operational review remain required before operational use."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--candidate-audit", type=Path, required=True)
    parser.add_argument("--case-heldout-gate", type=Path, required=True)
    parser.add_argument("--candidate-summary", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = evaluate(args.model_root, args.candidate_audit, args.case_heldout_gate, args.candidate_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

    if result["status"] == "candidate_incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
