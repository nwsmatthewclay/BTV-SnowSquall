"""Summarize modern candidate reconstruction evidence by case and radar."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(inventory_csv: Path, mrms_csv: Path, surface_csv: Path, output_json: Path, output_csv: Path):
    inv = pd.read_csv(inventory_csv)
    mrms = pd.read_csv(mrms_csv) if mrms_csv.exists() else pd.DataFrame()
    surface = pd.read_csv(surface_csv) if surface_csv.exists() else pd.DataFrame()

    rows = []
    for row in inv.itertuples(index=False):
        case_id = str(row.case_id)
        radar = str(row.radar_site)
        item = {
            "case_id": case_id,
            "episode_id": str(row.episode_id),
            "year": int(row.year),
            "radar_site": radar,
            "replay_attempted_scans": int(row.replay_attempted_scans),
            "replay_successful_scans": int(row.replay_successful_scans),
            "replay_failed_scans": int(row.replay_failed_scans),
            "replay_failure_rate": float(row.replay_failure_rate) if pd.notna(row.replay_failure_rate) else None,
            "replay_object_scan_count": int(row.replay_object_scan_count),
            "surface_station_count": int(row.surface_station_count),
            "surface_row_counts": str(row.surface_row_counts),
            "mrms_lcref_file_count": int(row.mrms_lcref_file_count),
            "truth_status": str(row.truth_status),
            "probability_status": str(row.probability_status),
            "training_eligible": False,
        }

        if not mrms.empty:
            m = mrms[
                (mrms["case_id"].astype(str) == case_id)
                & (
                    (mrms.get("radar_site", pd.Series(index=mrms.index, dtype=object)).astype(str) == radar)
                    if "radar_site" in mrms else True
                )
            ]
            paired = m[
                ["level2_max_reflectivity_dbz", "mrms_neighborhood_max_dbz"]
            ].apply(pd.to_numeric, errors="coerce").dropna() if not m.empty else pd.DataFrame()
            item["mrms_compared_records"] = int(len(m))
            item["mrms_paired_records"] = int(len(paired))
            item["mrms_max_age_minutes"] = (
                float(m["mrms_age_minutes"].max()) if not m.empty else None
            )
            if len(paired) >= 3:
                item["mrms_pearson_r"] = float(
                    paired["level2_max_reflectivity_dbz"].corr(
                        paired["mrms_neighborhood_max_dbz"]
                    )
                )
                diff = (
                    paired["mrms_neighborhood_max_dbz"].to_numpy()
                    - paired["level2_max_reflectivity_dbz"].to_numpy()
                )
                item["mrms_mean_abs_difference_dbz"] = float(abs(diff).mean())
                item["mrms_mean_signed_difference_dbz"] = float(diff.mean())

        if not surface.empty:
            s = surface[
                (surface["case_id"].astype(str) == case_id)
                & (surface["radar_site"].astype(str) == radar)
            ]
            item["surface_radar_records"] = int(len(s))
            vis = pd.to_numeric(s.get("visibility_mi"), errors="coerce").dropna() if not s.empty else pd.Series(dtype=float)
            if not vis.empty:
                item["surface_min_visibility_mi"] = float(vis.min())

        item["data_quality_status"] = (
            "ready_for_review"
            if item["replay_successful_scans"] > 0
            and (item["replay_failure_rate"] or 0.0) <= 0.20
            and item["surface_station_count"] > 0
            else "needs_review"
        )
        rows.append(item)

    df = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    payload = {
        "purpose": "modern candidate evidence summary",
        "training_eligible": False,
        "scoring_status": "not_scored",
        "cases": df.to_dict(orient="records"),
    }
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--mrms", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()
    build(
        Path(args.inventory),
        Path(args.mrms),
        Path(args.surface),
        Path(args.output_json),
        Path(args.output_csv),
    )


if __name__ == "__main__":
    main()
