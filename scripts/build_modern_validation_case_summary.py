"""Build a case-level non-scoring independent validation summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(cases_path: Path, inventory_path: Path, output_json: Path, output_csv: Path) -> dict:
    cases = pd.read_csv(cases_path)
    inventory = {
        c["case_id"]: c
        for c in json.loads(inventory_path.read_text(encoding="utf-8")).get("cases", [])
    }

    rows = []
    for row in cases.itertuples(index=False):
        case_id = str(row.case_id)
        if str(row.reconstruction_eligible).lower() != "true":
            continue

        surface_path = Path("data/raw/modern_surface") / str(row.observing_station) / f"{case_id}.csv"
        surface_diag = Path("data/derived") / f"modern_surface_radar_diagnostic_{case_id}.json"

        item = {
            "case_id": case_id,
            "event_date_utc": str(row.event_date_utc),
            "radar_site": str(row.radar_site),
            "observing_station": str(row.observing_station),
            "evidence_type": str(row.evidence_type),
            "evidence_source": str(row.evidence_source),
            "source_url": str(row.source_url),
            "reconstruction_eligible": True,
            "analysis_window_start_utc": str(row.analysis_window_start_utc),
            "analysis_window_end_utc": str(row.analysis_window_end_utc),
            "scoring_status": "not_scored",
            "probability_scored": False,
        }
        item.update({
            "replay_scans": inventory.get(case_id, {}).get("replay_scans", 0),
            "replay_failed_scans": inventory.get(case_id, {}).get("replay_failed_scans", 0),
            "replay_failure_rate": inventory.get(case_id, {}).get("replay_failure_rate"),
            "replay_object_scan_count": inventory.get(case_id, {}).get("replay_object_scan_count", 0),
            "surface_rows": inventory.get(case_id, {}).get("surface_rows", 0),
            "minimum_visibility_mi": inventory.get(case_id, {}).get("min_visibility_mi"),
            "maximum_gust_kt": inventory.get(case_id, {}).get("max_gust_kt"),
            "mrms_lcref_files": inventory.get(case_id, {}).get("mrms_lcref_files", 0),
        })

        if surface_diag.exists():
            item.update(json.loads(surface_diag.read_text(encoding="utf-8")))

        mrms_diag = Path("data/derived/modern_validation_mrms_object_comparison.csv")
        if mrms_diag.exists():
            mrms = pd.read_csv(mrms_diag)
            mrms = mrms[mrms["case_id"].astype(str) == case_id].copy()
            item["mrms_object_records_compared"] = int(len(mrms))
            paired = mrms[["level2_max_reflectivity_dbz", "mrms_neighborhood_max_dbz"]].apply(
                pd.to_numeric, errors="coerce"
            ).dropna()
            item["mrms_paired_records"] = int(len(paired))
            item["mrms_max_age_minutes"] = (
                float(mrms["mrms_age_minutes"].max()) if "mrms_age_minutes" in mrms and not mrms.empty else None
            )
            if len(paired) >= 3:
                l2 = paired["level2_max_reflectivity_dbz"].to_numpy()
                mr = paired["mrms_neighborhood_max_dbz"].to_numpy()
                diff = mr - l2
                item["mrms_neighborhood_pearson_r"] = float(pd.Series(l2).corr(pd.Series(mr)))
                item["mrms_mean_absolute_difference_dbz"] = float((abs(diff)).mean())
                item["mrms_mean_signed_difference_dbz"] = float(diff.mean())
                item["mrms_median_absolute_difference_dbz"] = float(pd.Series(abs(diff)).median())

        rows.append(item)

    df = pd.DataFrame(rows)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "purpose": "case-level independent evidence summary",
        "training_eligible": False,
        "scoring_status": "not_scored",
        "cases": rows,
    }
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    df.to_csv(output_csv, index=False)
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()
    build(
        Path(args.cases),
        Path(args.inventory),
        Path(args.output_json),
        Path(args.output_csv),
    )


if __name__ == "__main__":
    main()
