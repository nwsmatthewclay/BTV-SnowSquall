"""Build a non-scoring reconstruction manifest for the selected modern cohort."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def build(cohort_path: Path, preflight_path: Path, output_path: Path) -> pd.DataFrame:
    cohort = pd.read_csv(cohort_path)
    preflight = pd.read_csv(preflight_path)

    candidates = cohort[
        cohort["selection_basis"] == "one_hash_selected_episode_per_year"
    ].copy()
    if candidates.empty:
        raise ValueError("No outcome-blind cohort candidates")

    available = preflight[
        preflight["archive_status"].eq("available")
        & (pd.to_numeric(preflight["level2_volume_count"], errors="coerce") > 0)
    ].copy()

    ids = set(candidates["case_id"].astype(str))
    available = available[available["case_id"].astype(str).isin(ids)].copy()
    if available.empty:
        raise ValueError("No selected candidates have archived Level-II coverage")

    available["reconstruction_status"] = "queued"
    available["truth_status"] = "not_established"
    available["probability_status"] = "not_scored"
    available["training_eligible"] = False
    available["selection_policy"] = (
        "outcome_blind_deterministic_year_coverage;two_radar_archive_available"
    )

    cols = [
        "case_id", "episode_id", "year",
        "episode_start_utc", "episode_end_utc",
        "window_start_utc", "window_end_utc",
        "radar_site", "level2_volume_count",
        "first_volume_utc", "last_volume_utc",
        "reconstruction_status", "truth_status",
        "probability_status", "training_eligible",
        "selection_policy",
    ]
    out = available[cols].sort_values(["year", "case_id", "radar_site"]).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(out.to_string(index=False))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.cohort), Path(args.preflight), Path(args.output))


if __name__ == "__main__":
    main()
