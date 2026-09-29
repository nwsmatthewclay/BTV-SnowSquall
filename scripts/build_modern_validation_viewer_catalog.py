"""Build the static validation viewer catalog from the case evidence summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(summary_csv: Path, output: Path) -> dict:
    df = pd.read_csv(summary_csv)
    records = df.fillna("").to_dict(orient="records")
    payload = {
        "version": "modern-validation-viewer-v1",
        "data_status": "independent_review_package",
        "scoring_status": "not_scored",
        "training_eligible": False,
        "truth_note": (
            "Independent validation evidence only. Candidate truth is not "
            "established automatically and probabilities are disabled."
        ),
        "cases": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "cases": len(records),
        "training_eligible": False,
        "scoring_status": "not_scored",
        "output": str(output),
    }, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.summary), Path(args.output))


if __name__ == "__main__":
    main()
