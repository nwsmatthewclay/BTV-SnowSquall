"""Build a descriptive, non-ranked independent validation sampling frame.

The frame preserves every discovered warning episode and assigns objective
strata (year, warning count, duration). It does not select winners or promote
any episode into the validation manifest.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def build(input_csv: Path, output_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(input_csv)
    if df.empty:
        raise ValueError("No SQW episodes available for sampling frame")

    out = df.copy()
    out["episode_start"] = pd.to_datetime(out["episode_start"], utc=True)
    out["episode_end"] = pd.to_datetime(out["episode_end"], utc=True)
    out["duration_minutes"] = (
        out["episode_end"] - out["episode_start"]
    ).dt.total_seconds() / 60.0
    out["year"] = out["episode_start"].dt.year.astype(int)
    out["warning_count"] = pd.to_numeric(out["warning_count"], errors="coerce").fillna(0).astype(int)

    def duration_bin(v: float) -> str:
        if v < 60:
            return "lt_60m"
        if v < 180:
            return "60_to_180m"
        return "ge_180m"

    def warning_bin(v: int) -> str:
        if v == 1:
            return "single_warning"
        if v <= 4:
            return "2_to_4_warnings"
        return "5plus_warnings"

    out["duration_stratum"] = out["duration_minutes"].map(duration_bin)
    out["warning_count_stratum"] = out["warning_count"].map(warning_bin)
    out["review_status"] = "candidate_review_required"
    out["truth_role"] = "validation_candidate"
    out["reconstruction_eligible"] = False
    out["training_eligible"] = False
    out["selection_policy"] = "descriptive_sampling_frame_no_rank"

    cols = [
        "episode_id", "episode_start", "episode_end", "duration_minutes",
        "warning_count", "year", "years", "duration_stratum",
        "warning_count_stratum", "first_warning_issue", "last_warning_expire",
        "review_status", "truth_role", "reconstruction_eligible",
        "training_eligible", "selection_policy",
    ]
    out = out[cols].sort_values(["year", "episode_start"]).reset_index(drop=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)
    print(out.to_string(index=False))
    print(f"Sampling frame contains {len(out)} independent episode candidates.")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
