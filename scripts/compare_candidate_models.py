"""Compare research candidate model artifacts without selecting an operational winner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def load_metrics(root: Path):
    rows = []
    for p in sorted(root.glob("*_*/metrics.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
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
        })
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
