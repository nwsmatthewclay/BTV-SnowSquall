"""Audit positive-label distribution by historical case for a completed pilot artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("labeled_csv")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    d = pd.read_csv(args.labeled_csv)
    horizons = (15, 30, 45, 60)
    rows = []

    for case_id, g in d.groupby("case_id", dropna=False, sort=True):
        row = {
            "case_id": None if pd.isna(case_id) else str(case_id),
            "records": int(len(g)),
            "track_associated_records": int(g["track_event_associated"].fillna(False).sum()),
        }
        for h in horizons:
            target = f"squall_onset_within_{h}m"
            row[f"positive_{h}m"] = int(g[target].fillna(0).eq(1).sum())
        rows.append(row)

    summary = {
        "records": int(len(d)),
        "unique_case_ids": int(d["case_id"].nunique(dropna=True)),
        "cases": rows,
        "overall": {
            f"positive_{h}m": int(d[f"squall_onset_within_{h}m"].fillna(0).eq(1).sum())
            for h in horizons
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("Positive-label distribution by case")
    print(pd.DataFrame(rows).to_string(index=False))
    print("Overall:", json.dumps(summary["overall"], sort_keys=True))


if __name__ == "__main__":
    main()
