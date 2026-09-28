"""Enforce separation between modern independent validation and development data."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


MODERN = Path("data/manifests/modern_independent_validation_cases.csv")


def case_ids(path: Path) -> set[str]:
    if not path.exists() or path.suffix.lower() != ".csv":
        return set()
    try:
        df = pd.read_csv(path, usecols=lambda c: c in {"case_id", "case_ids"})
    except Exception:
        return set()
    ids: set[str] = set()
    for col in ("case_id", "case_ids"):
        if col in df.columns:
            for value in df[col].dropna().astype(str):
                ids.update(x.strip() for x in value.split(",") if x.strip())
    return ids


def audit(modern_path: Path, development_paths: list[Path]) -> dict:
    modern_df = pd.read_csv(modern_path)
    if "case_id" not in modern_df:
        raise ValueError("Modern validation manifest missing case_id")
    modern = set(modern_df["case_id"].dropna().astype(str))
    overlaps = {}

    for path in development_paths:
        ids = case_ids(path)
        overlap = sorted(modern & ids)
        if overlap:
            overlaps[str(path)] = overlap

    summary = {
        "modern_case_count": len(modern),
        "development_files_checked": len(development_paths),
        "overlaps": overlaps,
        "training_separation_ok": not overlaps,
    }
    if overlaps:
        raise ValueError(f"Modern validation case overlap detected: {overlaps}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modern", default=str(MODERN))
    parser.add_argument(
        "--development",
        nargs="*",
        default=[
            "data/manifests/banacos_2014_cases.csv",
            "data/manifests/banacos_pilot_cases.csv",
            "data/manifests/banacos_radar_windows.csv",
            "data/training/object_scans.csv",
            "data/training/training_table.csv",
        ],
    )
    args = parser.parse_args()
    summary = audit(Path(args.modern), [Path(p) for p in args.development])
    print(summary)


if __name__ == "__main__":
    main()
