"""Merge four archived replay horizons into one coherent research score timeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.probability_postprocess import monotone_cumulative_probabilities

HORIZONS = (15, 30, 45, 60)


def read_horizon(root: Path, horizon: int) -> dict[tuple[str, str], dict]:
    directory = root / f"{horizon}m"
    expected = f"probability_{horizon}min"
    rows = {}
    for path in sorted(directory.glob("*.geojson")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = payload.get("metadata") or {}
        scan_time = metadata.get("scan_time_utc")
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            track_id = props.get("track_id")
            if track_id is None:
                continue
            timestamp = props.get("timestamp") or scan_time
            key = (str(timestamp), str(track_id))
            item = rows.setdefault(
                key,
                {
                    "timestamp": timestamp,
                    "track_id": str(track_id),
                    "radar_site": props.get("radar_site"),
                    "max_reflectivity_dbz": props.get("max_reflectivity_dbz"),
                    "horizons": {},
                },
            )
            value = props.get(expected)
            if value is not None:
                item["horizons"][str(horizon)] = float(value)
    return rows


def merge(root: Path) -> dict:
    merged = {}
    by_horizon = {}
    for horizon in HORIZONS:
        rows = read_horizon(root, horizon)
        by_horizon[horizon] = rows
        for key, item in rows.items():
            target = merged.setdefault(key, dict(item))
            target["horizons"].update(item["horizons"])

    records = []
    alignment_gaps = []
    for key in sorted(merged):
        record = merged[key]
        expected_presence = {
            str(h): key in by_horizon[h]
            for h in HORIZONS
        }
        if len(set(expected_presence.values())) > 1:
            alignment_gaps.append(
                {
                    "timestamp": record["timestamp"],
                    "track_id": record["track_id"],
                    "horizon_presence": expected_presence,
                }
            )
        projected = monotone_cumulative_probabilities(record["horizons"])
        record["raw_cumulative_probabilities"] = dict(record["horizons"])
        record["cumulative_probabilities"] = projected.get("cumulative", {}) if projected else {}
        record["interval_probabilities"] = projected.get("interval", {}) if projected else {}
        record["probability_projection"] = (
            "isotonic_non_decreasing_horizon"
            if projected else "unavailable"
        )
        del record["horizons"]
        records.append(record)

    report = {
        "mode": "archived_research_replay_score_timeline",
        "operational_release_status": "candidate_only_not_operational",
        "future_information_policy": "one_scan_at_a_time",
        "record_count": len(records),
        "alignment_gap_count": len(alignment_gaps),
        "alignment_gaps": alignment_gaps,
        "records": records,
        "status": "pass" if records and not alignment_gaps else ("fail" if alignment_gaps else "empty"),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = merge(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "record_count": report["record_count"],
        "alignment_gap_count": report["alignment_gap_count"],
    }, indent=2))
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
