"""Create a human-review worksheet for modern reconstruction candidates.

This artifact intentionally contains no severity ranking, model scores, or
automatic truth decisions.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED = {
    "case_id", "episode_id", "year", "episode_start_utc", "episode_end_utc",
    "radar_site", "level2_volume_count",
}


def build(manifest_path: Path, output_path: Path) -> pd.DataFrame:
    df = pd.read_csv(manifest_path)
    missing = sorted(REQUIRED - set(df.columns))
    if missing:
        raise ValueError(f"Candidate manifest missing columns: {missing}")

    out = (
        df.sort_values(["year", "case_id", "radar_site"])
        .drop_duplicates("case_id")
        .loc[:, [
            "case_id", "episode_id", "year",
            "episode_start_utc", "episode_end_utc",
            "window_start_utc", "window_end_utc",
            "level2_volume_count",
        ]]
        .copy()
    )
    out["documentation_found"] = ""
    out["independent_impact_evidence_found"] = ""
    out["surface_visibility_evidence_found"] = ""
    out["surface_wind_evidence_found"] = ""
    out["radar_reconstruction_quality"] = ""
    out["cross_sensor_agreement"] = ""
    out["event_truth_status"] = "not_established"
    out["reviewer_notes"] = ""
    out["training_eligible"] = False
    out["probability_status"] = "not_scored"
    out["review_policy"] = "human_review_required;no_outcome_ranking"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(out.to_string(index=False))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.manifest), Path(args.output))


if __name__ == "__main__":
    main()
