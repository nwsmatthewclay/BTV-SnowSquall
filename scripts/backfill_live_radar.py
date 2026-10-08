#!/usr/bin/env python3
"""Backfill every missed KCXX cycle and its synchronized KTYX companion.

The public publisher runs on a coarse schedule, while NEXRAD scans arrive more
often.  This bridge treats the last published KCXX scan as a durable watermark,
discovers every KCXX volume newer than that watermark, and processes them in
chronological order.  Each KCXX cycle gets its own best-available KTYX volume
at or before the KCXX time.  This preserves object tracking continuity and
fills the radar-history archive instead of jumping straight to the newest scan.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from acquisition.radar_watcher import find_recent_volumes, make_s3_client


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def object_scan_time(live_root: Path, site: str) -> datetime | None:
    """Return the newest durable object timestamp for one radar."""
    candidates: list[datetime] = []
    state_path = live_root / f"{site}_state.json"
    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            parsed = parse_time(payload.get("last_scan_time_utc"))
            if parsed:
                candidates.append(parsed)
        except Exception:
            pass
    geo_path = live_root / f"{site}_objects.geojson"
    if geo_path.exists():
        try:
            payload = json.loads(geo_path.read_text(encoding="utf-8"))
            parsed = parse_time((payload.get("metadata") or {}).get("scan_time_utc"))
            if parsed:
                candidates.append(parsed)
        except Exception:
            pass
    return max(candidates) if candidates else None


def published_time(live_root: Path) -> datetime | None:
    """Return the oldest live watermark so any lagging object feed is caught up."""
    candidates: list[datetime] = []

    event = live_root / "event_cycle.json"
    if event.exists():
        try:
            payload = json.loads(event.read_text(encoding="utf-8"))
            parsed = parse_time((payload.get("kcxx") or {}).get("scan_time_utc"))
            if parsed:
                candidates.append(parsed)
        except Exception:
            pass

    radar = live_root / "radar_mosaic.json"
    if radar.exists():
        try:
            payload = json.loads(radar.read_text(encoding="utf-8"))
            for source in payload.get("sources", []):
                if source.get("radar") == "KCXX":
                    parsed = parse_time(source.get("scan_time_utc"))
                    if parsed:
                        candidates.append(parsed)
        except Exception:
            pass

    object_times = [
        object_scan_time(live_root, "KCXX"),
        object_scan_time(live_root, "KTYX"),
    ]
    candidates.extend(value for value in object_times if value is not None)
    return min(candidates) if candidates else None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-root", type=Path, default=Path("viewer/data/live"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--max-cycles", type=int, default=12)
    parser.add_argument("--lookback-hours", type=int, default=4)
    parser.add_argument("--kcxx-tolerance-minutes", type=float, default=4.0)
    parser.add_argument("--ktyx-max-age-minutes", type=float, default=8.0)
    parser.add_argument("--archive-attempts", type=int, default=6)
    parser.add_argument("--archive-delay-seconds", type=int, default=20)
    args = parser.parse_args()

    previous = published_time(args.live_root)
    s3 = make_s3_client()

    # Do not use only the newest published timestamp as the backfill watermark.
    # The live publisher can legitimately process the newest volume while
    # missing one or more intermediate scans.  In that situation the newest
    # timestamp looks healthy even though the track history has a hole.
    #
    # Instead, inspect the durable processed_sources ledger and recover every
    # recent KCXX volume that is not actually recorded there.  process_live_event
    # then processes those scans chronologically, preserving tracker continuity
    # and filling the radar-history archive at the same time.
    state_path = args.live_root / "KCXX_state.json"
    processed_sources = set()
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            processed_sources = {
                Path(str(value)).name
                for value in (state.get("processed_sources") or [])
                if value
            }
        except (OSError, json.JSONDecodeError, TypeError):
            processed_sources = set()

    all_recent = find_recent_volumes(
        s3, "KCXX", since=None, lookback_hours=args.lookback_hours
    )
    candidates = [
        item for item in all_recent
        if Path(item[0]).name not in processed_sources
    ]

    print(
        "Backfill watermark:",
        previous.isoformat() if previous else "none",
        "| recent KCXX volumes:",
        len(all_recent),
        "| unprocessed:",
        len(candidates),
    )

    if not candidates:
        print("No unprocessed KCXX scans are available.")
        return 0

    if len(candidates) > args.max_cycles:
        print(
            f"Found {len(candidates)} unprocessed KCXX scans; processing the oldest "
            f"{args.max_cycles} this run so the next scheduled run continues the backfill."
        )
        candidates = candidates[:args.max_cycles]

    print(
        f"Backfilling {len(candidates)} KCXX cycles from "
        f"{candidates[0][1].isoformat()} through {candidates[-1][1].isoformat()}."
    )

    for index, (_, scan_time) in enumerate(candidates, start=1):
        stamp = scan_time.isoformat().replace("+00:00", "Z")
        print(f"=== BACKFILL {index}/{len(candidates)}: KCXX {stamp} ===")
        cmd = [
            sys.executable,
            "scripts/process_live_event.py",
            "--scan-time", stamp,
            "--raw-root", str(args.raw_root),
            "--live-root", str(args.live_root),
            "--kcxx-tolerance-minutes", str(args.kcxx_tolerance_minutes),
            "--ktyx-max-age-minutes", str(args.ktyx_max_age_minutes),
            "--archive-attempts", str(args.archive_attempts),
            "--archive-delay-seconds", str(args.archive_delay_seconds),
        ]
        subprocess.run(cmd, check=True)

    print("LIVE RADAR BACKFILL COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
