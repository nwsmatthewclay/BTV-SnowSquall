"""Audit whether every sampled null window produced usable radar object records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def audit(manifest_path: Path, objects_path: Path, min_fraction: float = 0.75, allow_incomplete: bool = False) -> dict:
    manifest = pd.read_csv(manifest_path)
    objects = pd.read_csv(objects_path)

    required_manifest = {"null_id"}
    required_objects = {"null_id", "scan_time_utc"}
    missing_manifest = sorted(required_manifest - set(manifest.columns))
    missing_objects = sorted(required_objects - set(objects.columns))
    if missing_manifest:
        raise ValueError(f"Manifest missing columns: {missing_manifest}")
    if missing_objects:
        raise ValueError(f"Object file missing columns: {missing_objects}")

    expected = set(manifest["null_id"].dropna().astype(str))
    observed = set(objects["null_id"].dropna().astype(str))
    populated = expected & observed
    empty = sorted(expected - observed)

    by_null = (
        objects.dropna(subset=["null_id"])
        .assign(null_id=lambda d: d["null_id"].astype(str))
        .groupby("null_id")
        .agg(
            object_records=("null_id", "size"),
            scan_count=("scan_time_utc", "nunique"),
            radar_count=("radar_site", "nunique") if "radar_site" in objects.columns else ("null_id", "size"),
        )
        .reset_index()
    )

    fraction = len(populated) / len(expected) if expected else 0.0
    summary = {
        "expected_null_windows": len(expected),
        "populated_null_windows": len(populated),
        "empty_null_windows": len(empty),
        "population_fraction": fraction,
        "empty_null_ids": empty,
        "minimum_population_fraction": min_fraction,
        "passed": fraction >= min_fraction,
        "gate_mode": "advisory_incomplete_allowed" if allow_incomplete else "blocking",
        "window_details": by_null.to_dict(orient="records"),
    }

    if fraction < min_fraction and not allow_incomplete:
        raise ValueError(
            f"Only {len(populated)}/{len(expected)} null windows produced objects "
            f"({fraction:.1%}); minimum is {min_fraction:.1%}. Empty: {empty}"
        )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("objects")
    parser.add_argument("--report", required=True)
    parser.add_argument("--min-fraction", type=float, default=0.75)
    parser.add_argument("--allow-incomplete", action="store_true", help="Write a failed coverage report without raising.")
    args = parser.parse_args()

    summary = audit(
        Path(args.manifest),
        Path(args.objects),
        min_fraction=args.min_fraction,
        allow_incomplete=args.allow_incomplete,
    )
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
