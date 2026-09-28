"""Build a non-scoring inventory for modern independent validation cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(cases_path: Path, replay_root: Path, surface_root: Path, mrms_root: Path) -> dict:
    cases = pd.read_csv(cases_path)
    eligible = cases[
        cases["reconstruction_eligible"].astype(str).str.lower() == "true"
    ].copy()

    case_rows = []
    for row in eligible.itertuples(index=False):
        case_id = str(row.case_id)
        replay_manifest = replay_root / case_id / "replay_manifest.json"
        surface_file = surface_root / str(row.observing_station) / f"{case_id}.csv"

        replay = json.loads(replay_manifest.read_text()) if replay_manifest.exists() else {}
        surface = pd.read_csv(surface_file) if surface_file.exists() else pd.DataFrame()

        mrms_case = mrms_root / case_id
        mrms_files = sorted(mrms_case.glob("mrms_lcref_*.nc")) if mrms_case.exists() else []

        row_out = {
            "case_id": case_id,
            "radar_site": str(row.radar_site),
            "observing_station": str(row.observing_station),
            "analysis_window_start_utc": str(row.analysis_window_start_utc),
            "analysis_window_end_utc": str(row.analysis_window_end_utc),
            "replay_scans": int(replay.get("scan_count", 0)),
            "replay_attempted_scans": int(replay.get("attempted_scan_count", replay.get("scan_count", 0))),
            "replay_failed_scans": int(replay.get("failed_scan_count", 0)),
            "replay_failure_rate": (
                float(replay.get("failed_scan_count", 0)) / float(replay.get("attempted_scan_count", 1))
                if replay.get("attempted_scan_count") else None
            ),
            "replay_object_scan_count": int(replay.get("object_scan_count", 0)),
            "surface_rows": int(len(surface)),
            "min_visibility_mi": (
                float(surface["visibility_mi"].min())
                if "visibility_mi" in surface and surface["visibility_mi"].notna().any()
                else None
            ),
            "max_gust_kt": (
                float(surface["wind_gust_kt"].max())
                if "wind_gust_kt" in surface and surface["wind_gust_kt"].notna().any()
                else None
            ),
            "mrms_lcref_files": len(mrms_files),
            "probability_scored": False,
        }
        case_rows.append(row_out)

    inventory = {
        "purpose": "independent modern validation inventory",
        "scoring_status": "not_scored",
        "training_eligible": False,
        "cases": case_rows,
    }
    out_json = cases_path.parent.parent / "derived" / "modern_validation_inventory.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(case_rows).to_csv(
        out_json.with_suffix(".csv"), index=False
    )
    print(json.dumps(inventory, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--surface-root", required=True)
    parser.add_argument("--mrms-root", required=True)
    args = parser.parse_args()
    build(
        Path(args.cases),
        Path(args.replay_root),
        Path(args.surface_root),
        Path(args.mrms_root),
    )


if __name__ == "__main__":
    main()
