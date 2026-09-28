"""Summarize case-held-out baseline metrics across forecast horizons."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(root: Path, horizons=(15, 30, 45, 60)):
    rows = []
    for horizon in horizons:
        path = root / f"baseline_model_{horizon}m" / "metrics.json"
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        metrics = report.get("metrics", {})
        climatology = metrics.get("climatology", {})
        rows.append({
            "horizon_minutes": horizon,
            "status": report.get("evaluation_status"),
            "training_rows": report.get("training_rows"),
            "independent_groups": report.get("training_groups"),
            "positive_rows": metrics.get("positive_rows"),
            "negative_rows": metrics.get("negative_rows"),
            "positive_case_group_count": report.get("positive_case_group_count"),
            "roc_auc": metrics.get("auc_roc"),
            "pr_auc": metrics.get("average_precision"),
            "brier_score": metrics.get("brier_score"),
            "climatology_brier_score": climatology.get("brier_score"),
            "brier_skill_vs_climatology": (
                1.0 - metrics["brier_score"] / climatology["brier_score"]
                if metrics.get("brier_score") is not None
                and climatology.get("brier_score") not in (None, 0)
                else None
            ),
        })
    if not rows:
        raise ValueError("No baseline horizon reports found.")
    return {
        "summary_version": "baseline_horizon_summary_v1",
        "interpretation": "exploratory_case_held_out_only",
        "horizons": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/derived")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = summarize(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["horizons"]:
        print(
            f"{row['horizon_minutes']}m: "
            f"rows={row['training_rows']} positives={row['positive_rows']} "
            f"ROC_AUC={row['roc_auc']} PR_AUC={row['pr_auc']} "
            f"Brier={row['brier_score']} climatology_Brier={row['climatology_brier_score']}"
        )


if __name__ == "__main__":
    main()
