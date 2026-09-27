"""Build the leakage-safe ML table from reconstructed object scans.

Expected input:
  data/training/object_scans.csv

The input is produced by radar reconstruction. This script:
1. adds past-only track evolution,
2. attaches published event truth by case_id,
3. creates 15/30/45/60 minute targets,
4. preserves provenance,
5. writes the portable training table.

It intentionally refuses to invent missing object observations or labels.
"""
from pathlib import Path
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from snow_squall.temporal import add_track_history_features
from snow_squall.labels import add_multi_horizon_targets

OBJECTS = ROOT / "data/training/object_scans.csv"
CASES = ROOT / "data/manifests/banacos_2014_cases.csv"
OUT = ROOT / "data/training/training_table.csv"

def main():
    if not OBJECTS.exists():
        raise SystemExit(
            "Missing data/training/object_scans.csv. Run radar reconstruction first."
        )

    objects = pd.read_csv(OBJECTS)
    required = {"case_id", "object_id", "scan_time"}
    missing = required - set(objects.columns)
    if missing:
        raise SystemExit(f"Object table missing required columns: {sorted(missing)}")

    cases = pd.read_csv(CASES)
    cases["event_start_utc"] = pd.to_datetime(cases["event_start_utc"], utc=True)

    objects = add_track_history_features(objects)
    objects["scan_time"] = pd.to_datetime(objects["scan_time"], utc=True, errors="coerce")
    objects = objects.merge(
        cases[["case_id", "event_start_utc", "label_status"]],
        on="case_id", how="left", validate="many_to_one"
    )

    objects["truth_onset_time"] = objects["event_start_utc"]
    objects["manual_label"] = objects["label_status"].where(
        objects["label_status"].notna(), "null"
    )
    objects["label_confidence"] = objects["label_status"].map(
        {"verified": "high"}
    ).fillna("unlabeled")
    objects["label_source"] = objects["label_status"].map(
        {"verified": "Banacos et al. 2014"}
    )

    objects = add_multi_horizon_targets(objects)
    objects["dataset_version"] = "v1"
    objects["provenance"] = "banacos_2014_case_manifest"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    objects.to_csv(OUT, index=False)
    print(f"Wrote {len(objects):,} rows to {OUT}")

if __name__ == "__main__":
    main()
