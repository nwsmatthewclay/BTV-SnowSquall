"""Produce a compact machine-readable health report for a live radar-object worker."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def healthcheck(state_path: Path, geojson_path: Path, max_age_minutes: float = 15.0) -> dict:
    now = datetime.now(timezone.utc)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    geo = json.loads(geojson_path.read_text(encoding="utf-8"))

    last_scan = parse_time(state["last_scan_time_utc"])
    age_minutes = (now - last_scan).total_seconds() / 60.0
    features = geo.get("features", [])
    metadata = geo.get("metadata", {})

    checks = {
        "state_present": bool(state.get("last_source")),
        "scan_timestamp_present": bool(state.get("last_scan_time_utc")),
        "geojson_contract": geo.get("type") == "FeatureCollection",
        "object_count_matches": int(state.get("last_object_count", -1)) == len(features),
        "probability_disabled": metadata.get("probability_status") == "not_scored",
        "fresh_within_threshold": age_minutes <= max_age_minutes,
    }
    healthy = all(checks.values())

    return {
        "status": "healthy" if healthy else "degraded",
        "checked_utc": now.isoformat(),
        "last_scan_time_utc": last_scan.isoformat(),
        "age_minutes": round(age_minutes, 2),
        "source_file": state.get("last_source"),
        "object_count": len(features),
        "probability_status": metadata.get("probability_status"),
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="data/derived/live_tracker_state.json")
    parser.add_argument("--geojson", default="data/derived/live_objects.geojson")
    parser.add_argument("--max-age-minutes", type=float, default=15.0)
    args = parser.parse_args()

    report = healthcheck(
        Path(args.state),
        Path(args.geojson),
        max_age_minutes=args.max_age_minutes,
    )
    print(json.dumps(report, indent=2))
    if report["status"] != "healthy":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
