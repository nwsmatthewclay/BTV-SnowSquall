"""Build a non-scoring inventory for modern candidate reconstructions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(manifest_path: Path, replay_root: Path, surface_root: Path, mrms_root: Path, output_json: Path, output_csv: Path):
    manifest = pd.read_csv(manifest_path)
    rows = []

    for row in manifest.itertuples(index=False):
        case_id = str(row.case_id)
        radar = str(row.radar_site)
        replay = replay_root / case_id / radar / "replay_manifest.json"
        data = json.loads(replay.read_text(encoding="utf-8")) if replay.exists() else {}

        surface_pairs = {}
        for path in sorted(surface_root.glob(f"*/{case_id}.csv")):
            station = path.parent.name
            try:
                surface_pairs[station] = len(pd.read_csv(path))
            except Exception:
                surface_pairs[station] = None

        mrms_case = mrms_root / case_id / radar
        mrms_count = len(list(mrms_case.glob("mrms_lcref_*.nc"))) if mrms_case.exists() else 0

        attempted = int(data.get("attempted_scan_count", 0))
        failed = int(data.get("failed_scan_count", 0))

        rows.append({
            "case_id": case_id,
            "episode_id": str(row.episode_id),
            "year": int(row.year),
            "radar_site": radar,
            "episode_start_utc": str(row.episode_start_utc),
            "episode_end_utc": str(row.episode_end_utc),
            "window_start_utc": str(row.window_start_utc),
            "window_end_utc": str(row.window_end_utc),
            "level2_manifest_volume_count": int(row.level2_volume_count),
            "replay_attempted_scans": attempted,
            "replay_successful_scans": int(data.get("successful_scan_count", 0)),
            "replay_failed_scans": failed,
            "replay_failure_rate": failed / attempted if attempted else None,
            "replay_object_scan_count": int(data.get("object_scan_count", 0)),
            "surface_station_count": len(surface_pairs),
            "surface_row_counts": json.dumps(surface_pairs, sort_keys=True),
            "mrms_lcref_file_count": mrms_count,
            "truth_status": str(row.truth_status),
            "probability_status": str(row.probability_status),
            "training_eligible": False,
        })

    df = pd.DataFrame(rows)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "purpose": "modern candidate reconstruction inventory",
        "training_eligible": False,
        "scoring_status": "not_scored",
        "records": rows,
    }
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    df.to_csv(output_csv, index=False)
    print(json.dumps(payload, indent=2))
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--surface-root", required=True)
    parser.add_argument("--mrms-root", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()
    build(
        Path(args.manifest),
        Path(args.replay_root),
        Path(args.surface_root),
        Path(args.mrms_root),
        Path(args.output_json),
        Path(args.output_csv),
    )


if __name__ == "__main__":
    main()
