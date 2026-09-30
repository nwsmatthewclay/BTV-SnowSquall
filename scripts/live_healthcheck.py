"""Produce a compact machine-readable health report for a live radar-object worker."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


SHADOW_HORIZONS = ("15", "30", "45", "60")
SHADOW_SITES = ("KCXX", "KTYX")


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)



def audit_shadow_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("mode") != "live_shadow_research":
        raise ValueError(f"{path}: unexpected shadow mode")
    if payload.get("operational_release_status") != "candidate_only_not_operational":
        raise ValueError(f"{path}: shadow feed is not marked candidate-only")
    records = payload.get("records") or []
    probability_count = 0
    monotone_failures = 0
    out_of_range = 0
    for record in records:
        probs = record.get("research_probabilities") or {}
        values = []
        for horizon in SHADOW_HORIZONS:
            value = probs.get(horizon)
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                out_of_range += 1
                continue
            if not 0.0 <= value <= 1.0:
                out_of_range += 1
            values.append(value)
            probability_count += 1
        if any(values[i] > values[i + 1] + 1e-12 for i in range(len(values) - 1)):
            monotone_failures += 1
    if out_of_range:
        raise ValueError(f"{path}: {out_of_range} invalid probabilities")
    if monotone_failures:
        raise ValueError(f"{path}: non-monotone cumulative horizons")
    return {
        "site": payload.get("site"),
        "record_count": len(records),
        "probability_count": probability_count,
        "scored_object_count": int(payload.get("scored_object_count", 0)),
        "status": "pass",
    }


def audit_shadow_root(root: Path) -> dict:
    rows = []
    for site in SHADOW_SITES:
        path = root / f"{site}_shadow.json"
        if not path.exists():
            raise ValueError(f"Missing shadow feed: {path}")
        rows.append(audit_shadow_payload(path))
    return {"status": "pass", "sites": rows}

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
    parser.add_argument("--shadow-root", default=None, help="Optional directory containing KCXX_shadow.json and KTYX_shadow.json.")
    args = parser.parse_args()

    report = healthcheck(
        Path(args.state),
        Path(args.geojson),
        max_age_minutes=args.max_age_minutes,
    )
    if args.shadow_root:
        try:
            report["shadow"] = audit_shadow_root(Path(args.shadow_root))
        except Exception as exc:
            report["shadow"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            report["status"] = "degraded"
    print(json.dumps(report, indent=2))
    if report["status"] != "healthy":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
