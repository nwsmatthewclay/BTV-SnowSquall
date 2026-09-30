"""Summarize an archived Snow Squall replay score timeline for research diagnostics.

This module never labels a case as successful or failed. It describes the
probability evolution actually produced by replay and can optionally compute
lead time relative to an independently supplied observed onset timestamp.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

HORIZONS = (15, 30, 45, 60)
THRESHOLDS = (0.10, 0.25, 0.50, 0.75)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def first_threshold(records: list[dict], horizon: int, threshold: float) -> str | None:
    key = str(horizon)
    for row in records:
        value = (row.get("cumulative_probabilities") or {}).get(key)
        if value is not None and float(value) >= threshold:
            return str(row.get("timestamp"))
    return None


def summarize(timeline: dict, onset_utc: str | None = None) -> dict:
    records = sorted(
        [r for r in timeline.get("records") or [] if r.get("timestamp")],
        key=lambda r: parse_time(r["timestamp"]),
    )

    tracks = sorted({str(r.get("track_id")) for r in records if r.get("track_id") is not None})
    horizons = {}
    for horizon in HORIZONS:
        values = [
            (parse_time(r["timestamp"]), float((r.get("cumulative_probabilities") or {})[str(horizon)]))
            for r in records
            if (r.get("cumulative_probabilities") or {}).get(str(horizon)) is not None
        ]
        peak = max(values, key=lambda item: item[1], default=None)
        horizons[str(horizon)] = {
            "record_count": len(values),
            "peak_probability": peak[1] if peak else None,
            "peak_timestamp_utc": peak[0].isoformat().replace("+00:00", "Z") if peak else None,
            "first_threshold_crossings_utc": {
                str(threshold): first_threshold(records, horizon, threshold)
                for threshold in THRESHOLDS
            },
        }

    lead_time = {}
    if onset_utc:
        onset = parse_time(onset_utc)
        for horizon, summary in horizons.items():
            for threshold, timestamp in summary["first_threshold_crossings_utc"].items():
                if timestamp is None:
                    lead_time.setdefault(horizon, {})[threshold] = None
                    continue
                lead_time.setdefault(horizon, {})[threshold] = round(
                    (onset - parse_time(timestamp)).total_seconds() / 60.0, 2
                )

    return {
        "mode": "archived_research_replay_diagnostics",
        "future_information_policy": timeline.get("future_information_policy", "one_scan_at_a_time"),
        "operational_release_status": "candidate_only_not_operational",
        "record_count": len(records),
        "track_count": len(tracks),
        "track_ids": tracks,
        "first_record_utc": records[0]["timestamp"] if records else None,
        "last_record_utc": records[-1]["timestamp"] if records else None,
        "horizons": horizons,
        "observed_onset_utc": onset_utc,
        "threshold_lead_time_minutes": lead_time,
        "alignment_gap_count": timeline.get("alignment_gap_count", 0),
        "replay_status": timeline.get("status", "unknown"),
        "timeline_integrity": {
            "records_present": bool(records),
            "alignment_gaps_clear": timeline.get("alignment_gap_count", 0) == 0,
            "future_information_policy": timeline.get("future_information_policy", "one_scan_at_a_time") == "one_scan_at_a_time",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("timeline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--onset-utc", default=None)
    args = parser.parse_args()

    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    report = summarize(timeline, args.onset_utc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
