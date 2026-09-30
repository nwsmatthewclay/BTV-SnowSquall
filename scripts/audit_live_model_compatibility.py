"""Audit learned snow-squall bundles for live feature compatibility.

This is a release-packaging guard, not a model-performance test. Every learned
bundle must use predictors that are explicitly part of the live-compatible
schema and must not contain label/truth/surface-observation fields.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.build_model_features import (
    BLOCKED_PREFIXES,
    NON_PREDICTOR_COLUMNS,
    OPERATIONAL_LIVE_PREDICTORS,
)


HORIZONS = (15, 30, 45, 60)
BUNDLE_PREFIXES = (
    "baseline_expansion_",
    "candidate_ensemble_expansion_",
    "baseline_refresh_",
    "candidate_ensemble_refresh_",
)


def audit_bundle(root: Path, schema: dict, prefix: str, horizon: int) -> dict:
    bundle = root / f"{prefix}{horizon}m"
    metrics_path = bundle / "metrics.json"
    if not metrics_path.exists():
        raise ValueError(f"Missing metrics.json: {metrics_path}")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    predictors = list(metrics.get("predictor_columns") or [])
    schema_live = set(schema.get("operational_predictor_columns") or [])
    runtime_predictors = set(predictors)
    live_missing = sorted(runtime_predictors - OPERATIONAL_LIVE_PREDICTORS)
    schema_missing = sorted(runtime_predictors - schema_live)
    blocked = sorted(
        c for c in predictors
        if c in NON_PREDICTOR_COLUMNS or c.startswith(BLOCKED_PREFIXES)
    )

    target = str(metrics.get("target") or "")
    expected_target = f"squall_onset_within_{horizon}m"

    if target != expected_target:
        raise ValueError(
            f"{bundle}: target={target!r}; expected {expected_target!r}"
        )
    if live_missing:
        raise ValueError(f"{bundle}: non-live predictors: {live_missing}")
    if schema_missing:
        raise ValueError(f"{bundle}: predictors absent from live schema: {schema_missing}")
    if blocked:
        raise ValueError(f"{bundle}: blocked predictors present: {blocked}")
    if not predictors:
        raise ValueError(f"{bundle}: empty predictor list")

    return {
        "bundle": bundle.name,
        "horizon_minutes": horizon,
        "predictor_count": len(predictors),
        "target": target,
        "operational_release_status": metrics.get("operational_release_status"),
        "status": "pass",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    rows = [
        audit_bundle(args.model_root, schema, prefix, horizon)
        for prefix in BUNDLE_PREFIXES
        for horizon in HORIZONS
    ]
    report = {
        "status": "pass",
        "future_information_policy": schema.get("future_information_policy"),
        "bundles_audited": len(rows),
        "bundles": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
