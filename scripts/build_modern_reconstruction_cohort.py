"""Build a deterministic, non-ranked modern reconstruction cohort.

Existing independently reconstructed validation cases are retained. For each
remaining year in the SQW candidate sampling frame, one episode is selected by
a stable SHA-256 hash of episode_id. The rule does not use surface impact,
reflectivity, warning duration, or model output.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


def choose_one(group: pd.DataFrame) -> pd.Series:
    ranked = group.copy()
    ranked["_hash"] = ranked["episode_id"].astype(str).map(
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    )
    return ranked.sort_values("_hash").iloc[0]


def build(frame_path: Path, existing_cases_path: Path, output_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(frame_path)
    existing = pd.read_csv(existing_cases_path)

    required_frame = {"episode_id", "episode_start", "episode_end", "year"}
    missing = required_frame - set(frame.columns)
    if missing:
        raise ValueError(f"Sampling frame missing required columns: {sorted(missing)}")

    existing_ids = set()
    if "case_id" in existing.columns:
        existing_ids = set(existing["case_id"].dropna().astype(str))

    rows = []
    for case_id in sorted(existing_ids):
        if not case_id.startswith("BTV"):
            continue
        rows.append({
            "case_id": case_id,
            "episode_id": case_id,
            "selection_basis": "already_reconstructed_independent_case",
            "selection_hash": "",
            "truth_role": "validation_candidate",
            "reconstruction_eligible": True,
        })

    candidates = frame[~frame["episode_id"].isin(existing_ids)].copy()
    for year, group in candidates.groupby("year", sort=True):
        chosen = choose_one(group)
        digest = hashlib.sha256(str(chosen["episode_id"]).encode("utf-8")).hexdigest()
        rows.append({
            "case_id": f"SQW{chosen['episode_id']}",
            "episode_id": str(chosen["episode_id"]),
            "year": int(year),
            "episode_start": str(chosen["episode_start"]),
            "episode_end": str(chosen["episode_end"]),
            "selection_basis": "one_hash_selected_episode_per_year",
            "selection_hash": digest,
            "truth_role": "reconstruction_candidate",
            "reconstruction_eligible": False,
        })

    result = pd.DataFrame(rows)
    if "year" not in result.columns:
        result["year"] = pd.Series(dtype="Int64")
    result = result.sort_values(["year", "episode_id"], na_position="first").reset_index(drop=True)
    result["selection_policy"] = (
        "outcome_blind_deterministic_year_coverage;no_ranking"
    )
    result["training_eligible"] = False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(result.to_string(index=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", required=True)
    parser.add_argument("--existing-cases", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.frame), Path(args.existing_cases), Path(args.output))


if __name__ == "__main__":
    main()
