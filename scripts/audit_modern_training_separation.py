"""Audit separation between modern independent candidates and development manifests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


CASE_COLUMNS = ("case_id", "window_id", "null_id")


def collect_ids(path: Path) -> set[str]:
    try:
        df = pd.read_csv(path)
    except Exception:
        return set()
    ids: set[str] = set()
    for column in CASE_COLUMNS:
        if column in df.columns:
            ids.update(df[column].dropna().astype(str).str.strip())
    return {x for x in ids if x}


def audit(modern_path: Path, development_root: Path) -> dict:
    modern = pd.read_csv(modern_path)
    if "case_id" not in modern.columns:
        raise ValueError("Modern cohort missing case_id")

    modern_ids = set(modern["case_id"].dropna().astype(str).str.strip())
    sources = []
    overlaps: dict[str, list[str]] = {}

    for path in sorted(development_root.rglob("*.csv")):
        if path.resolve() == modern_path.resolve():
            continue
        if "modern_" in path.name.lower():
            continue
        ids = collect_ids(path)
        overlap = sorted(modern_ids & ids)
        if overlap:
            overlaps[str(path)] = overlap
        if ids:
            sources.append({"path": str(path), "case_id_count": len(ids)})

    if overlaps:
        raise ValueError(f"modern_development_overlap:{overlaps}")

    return {
        "modern_case_count": len(modern_ids),
        "development_manifest_count": len(sources),
        "training_eligible": False,
        "overlaps": {},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modern", required=True)
    parser.add_argument("--development-root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = audit(Path(args.modern), Path(args.development_root))
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
