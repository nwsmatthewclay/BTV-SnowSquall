"""Join SQW episode structure with observed surface-impact evidence.

This remains descriptive and review-only. No episode is selected or labeled as
snow-squall truth by this utility.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def build(frame_path: Path, surface_path: Path, output_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(frame_path)
    surface = pd.read_csv(surface_path)

    if frame.empty:
        raise ValueError("Sampling frame is empty")
    if surface.empty:
        raise ValueError("Surface impact inventory is empty")

    for col in ("episode_id",):
        if col not in frame.columns or col not in surface.columns:
            raise ValueError(f"Missing join column: {col}")

    surface["min_visibility_mi"] = pd.to_numeric(
        surface["min_visibility_mi"], errors="coerce"
    )
    if "snow_code_at_visibility_min" not in surface.columns:
        surface["snow_code_at_visibility_min"] = False
    if "visibility_drop_from_baseline_mi" not in surface.columns:
        surface["visibility_drop_from_baseline_mi"] = pd.NA
    surface["max_wind_gust_kt"] = pd.to_numeric(
        surface["max_wind_gust_kt"], errors="coerce"
    )

    agg = (
        surface.groupby("episode_id", as_index=False)
        .agg(
            stations_queried=("station", "nunique"),
            successful_station_queries=("query_status", lambda s: int((s == "success").sum())),
            minimum_visibility_mi=("min_visibility_mi", "min"),
            maximum_gust_kt=("max_wind_gust_kt", "max"),
            stations_visibility_le_0p5_sm=("min_visibility_mi", lambda s: int((s <= 0.5).sum())),
            stations_visibility_le_0p25_sm=("min_visibility_mi", lambda s: int((s <= 0.25).sum())),
            stations_with_present_weather=("present_weather_codes", lambda s: int(s.astype(str).str.strip().ne("").sum())),
            stations_snow_coded_at_visibility_min=("snow_code_at_visibility_min", lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())),
            minimum_visibility_drop_from_baseline_mi=("visibility_drop_from_baseline_mi", "max"),
        )
    )

    result = frame.merge(agg, on="episode_id", how="left", validate="one_to_one")
    result["surface_evidence_review_status"] = result.apply(
        lambda r: (
            "surface_visibility_at_or_below_0p25_sm"
            if pd.notna(r["minimum_visibility_mi"]) and r["minimum_visibility_mi"] <= 0.25
            else "surface_visibility_at_or_below_0p5_sm"
            if pd.notna(r["minimum_visibility_mi"]) and r["minimum_visibility_mi"] <= 0.5
            else "surface_data_available"
            if pd.notna(r["minimum_visibility_mi"])
            else "no_surface_visibility"
        ),
        axis=1,
    )
    result["review_status"] = "candidate_review_required"
    result["truth_role"] = "validation_candidate"
    result["reconstruction_eligible"] = False
    result["training_eligible"] = False
    result["selection_policy"] = "descriptive_evidence_matrix_no_rank"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(result.to_string(index=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.frame), Path(args.surface), Path(args.output))


if __name__ == "__main__":
    main()
