"""Audit a reconstructed Level-II object table and its volume-error log."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def audit(objects_path: Path, errors_path: Path) -> dict:
    objects = pd.read_csv(objects_path)
    errors = pd.read_csv(errors_path)

    required = {"source_file", "reader_backend"}
    missing = required - set(objects.columns)
    if missing:
        raise ValueError(f"Object reconstruction missing required columns: {sorted(missing)}")

    object_volume_counts = objects.groupby("reader_backend", dropna=False)["source_file"].nunique()
    failed = set(errors["source_file"].dropna().astype(str)) if "source_file" in errors else set()
    observed = set(objects["source_file"].dropna().astype(str))
    backend_counts = {
        str(k): int(v) for k, v in object_volume_counts.items()
    }

    summary = {
        "object_records": int(len(objects)),
        "volumes_with_candidate_objects": int(len(observed)),
        "failed_volumes": int(len(failed)),
        "reader_backend_volume_counts": backend_counts,
        "error_type_counts": (
            errors["error_type"].value_counts(dropna=False).to_dict()
            if "error_type" in errors.columns else {}
        ),
        "error_files_with_object_records": int(len(failed & observed)),
        "objects_with_missing_reader_backend": int(objects["reader_backend"].isna().sum()),
    }

    # A file should never simultaneously be listed as failed and contribute
    # candidate objects unless a future retry strategy explicitly records this.
    if failed & observed:
        raise ValueError(
            f"{len(failed & observed)} failed source files also appear in the object table"
        )

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("objects_csv")
    parser.add_argument("--errors", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    summary = audit(Path(args.objects_csv), Path(args.errors))
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2) + "\\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
