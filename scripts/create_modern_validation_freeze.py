"""Create a reproducible freeze record for modern independent validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build(modern_path: Path, output: Path, repo_root: Path) -> dict:
    modern = pd.read_csv(modern_path)
    modern_ids = set(modern["case_id"].astype(str))

    development_manifests = []
    overlaps = {}
    for path in sorted((repo_root / "data/manifests").glob("*.csv")):
        if path.resolve() == modern_path.resolve():
            continue
        try:
            df = pd.read_csv(path, nrows=0)
        except Exception:
            continue
        if "case_id" not in df.columns:
            continue
        full = pd.read_csv(path, usecols=["case_id"])
        ids = set(full["case_id"].dropna().astype(str))
        overlap = sorted(modern_ids & ids)
        development_manifests.append(str(path.relative_to(repo_root)))
        if overlap:
            overlaps[str(path.relative_to(repo_root))] = overlap

    if overlaps:
        raise ValueError(f"Modern validation IDs overlap development manifests: {overlaps}")

    payload = {
        "purpose": "frozen modern independent validation provenance",
        "training_eligible": False,
        "scoring_status": "not_scored",
        "verification_revision": "GITHUB_SHA_REQUIRED_AT_WORKFLOW_RUNTIME",
        "modern_manifest": str(modern_path.relative_to(repo_root)),
        "modern_manifest_sha256": sha256(modern_path),
        "case_ids": sorted(modern_ids),
        "development_manifests_checked": development_manifests,
        "overlaps": overlaps,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modern", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    build(Path(args.modern), Path(args.output), Path(args.repo_root).resolve())


if __name__ == "__main__":
    main()
