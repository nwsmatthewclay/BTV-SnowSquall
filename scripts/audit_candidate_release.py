"""Audit a candidate model release package without enabling operational use."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.audit_live_model_compatibility import audit_bundle, HORIZONS

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", type=Path, required=True)
    ap.add_argument("--model-root", type=Path, required=True)
    ap.add_argument("--prefix", default="candidate_ensemble_refresh_")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    rows = []
    targets = []
    predictors = []
    for h in HORIZONS:
        bundle = args.model_root / f"{args.prefix}{h}m"
        metrics_path = bundle / "metrics.json"
        model_path = bundle / "baseline_model.joblib"
        calibrator_path = bundle / "probability_calibrator.joblib"
        if not metrics_path.exists() or not model_path.exists() or not calibrator_path.exists():
            raise SystemExit(f"FAIL: incomplete bundle for {h}m: {bundle}")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics.get("calibration_status") != "fit_on_oof_research_data":
            raise SystemExit(f"FAIL: {h}m bundle missing OOF calibration status")
        if metrics.get("operational_release_status") not in {"candidate_only", "candidate_only_not_operational"}:
            raise SystemExit(f"FAIL: {h}m bundle has unexpected release status {metrics.get("operational_release_status")!r}")
        row = audit_bundle(args.model_root, schema, args.prefix.replace("_refresh_", "_refresh_"), h)
        row["calibration_status"] = metrics.get("calibration_status")
        row["calibration_method"] = metrics.get("calibration_method")
        rows.append(row)
        targets.append(metrics.get("target"))
        predictors.append(tuple(metrics.get("predictor_columns") or []))

    if targets != [f"squall_onset_within_{h}m" for h in HORIZONS]:
        raise SystemExit(f"FAIL: horizon targets are not ordered as expected: {targets}")
    if len({p for p in predictors}) != 1:
        raise SystemExit("FAIL: predictor contracts differ across the four horizon bundles")

    report = {
        "status": "pass",
        "release_status": "candidate_only_not_operational",
        "future_information_policy": schema.get("future_information_policy"),
        "bundle_prefix": args.prefix,
        "bundles_audited": len(rows),
        "common_predictor_count": len(predictors[0]),
        "calibration_required": True,
        "bundles": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
