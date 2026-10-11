"""Compare research candidate model artifacts without selecting an operational winner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _calibration_summary(model_dir: Path, target: str) -> dict:
    """Flatten the grouped/temporal calibration report into comparison columns."""
    report_path = model_dir / "calibration_report.json"
    if not report_path.exists():
        return {"calibration_status": "not_available"}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"calibration_status": "invalid_report"}

    import re
    match = re.search(r"within_(15|30|45|60)m$", str(target))
    horizon = match.group(1) if match else None
    item = (report.get("horizons") or {}).get(horizon, {}) if horizon else {}
    evaluation = item.get("cross_fitted_evaluation") or {}
    raw = evaluation.get("raw_oof_probability_metrics") or {}
    calibrated = evaluation.get("cross_fitted_calibrated_probability_metrics") or {}
    return {
        "calibration_status": item.get("status", "not_available"),
        "calibration_report_status": report.get("status"),
        "calibration_method": evaluation.get("method"),
        "calibration_temporal_ordering_enforced": evaluation.get("temporal_ordering_enforced"),
        "calibration_evaluated_rows": evaluation.get("evaluated_rows"),
        "raw_oof_brier_score": raw.get("brier_score"),
        "cross_fitted_calibrated_brier_score": calibrated.get("brier_score"),
        "raw_oof_log_loss": raw.get("log_loss"),
        "cross_fitted_calibrated_log_loss": calibrated.get("log_loss"),
        "raw_oof_ece": raw.get("expected_calibration_error_equal_frequency"),
        "cross_fitted_calibrated_ece": calibrated.get("expected_calibration_error_equal_frequency"),
        "raw_brier_skill_vs_fold_climatology": raw.get("brier_skill_vs_fold_climatology"),
        "calibrated_brier_skill_vs_fold_climatology": calibrated.get("brier_skill_vs_fold_climatology"),
    }


def load_metrics(root: Path):
    rows = []
    for p in sorted(root.glob("*_*/metrics.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        row = {
            "model_dir": p.parent.name,
            "model_version": m.get("model_version"),
            "target": m.get("target"),
            "evaluation_status": m.get("evaluation_status"),
            "training_rows": m.get("training_rows"),
            "training_groups": m.get("training_groups"),
            "positive_group_count": m.get("positive_case_group_count"),
            "auc_roc": (m.get("metrics") or {}).get("auc_roc"),
            "average_precision": (m.get("metrics") or {}).get("average_precision"),
            "brier_score": (m.get("metrics") or {}).get("brier_score"),
            "operational_release_status": m.get("operational_release_status"),
        }
        row.update(_calibration_summary(p.parent, m.get("target", "")))
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    table = load_metrics(Path(args.root))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(Path(args.output).with_suffix(".csv"), index=False)

    summary = {
        "models_compared": int(len(table)),
        "policy": "Descriptive comparison only. No model is selected or endorsed for operational use.",
        "rows": table.to_dict("records"),
    }
    Path(args.output).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
