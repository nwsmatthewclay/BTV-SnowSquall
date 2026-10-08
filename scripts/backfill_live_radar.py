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
from datetime import datetime, timedelta, timezone
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
    """Return the durable KCXX publication watermark for KCXX backfill.

    KTYX is a synchronized companion selected for each KCXX event. Using the
    older KTYX timestamp as the KCXX watermark causes the backfill to revisit
    scans that are no longer present in the near-real-time archive. The KCXX
    feed is therefore the authoritative watermark here.
    """
    candidates: list[datetime] = []

    event = live_root / "event_cycle.json"
    if event.exists():
        try:
            payload = json.loads(event.read_text(encoding="utf-8"))
            parsed = parse_time((payload.get("kcxx") or {}).get("scan_time_utc"))
            if parsed:
                candidates.append(parsed)
        except (OSError, json.JSONDecodeError, TypeError):
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
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    kcxx_time = object_scan_time(live_root, "KCXX")
    if kcxx_time:
        candidates.append(kcxx_time)

    return max(candidates) if candidates else None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radar", default="KCXX", choices=("KCXX", "KTYX"))
    parser.add_argument("--live-root", type=Path, default=Path("viewer/data/live"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--max-cycles", type=int, default=12)
    parser.add_argument("--lookback-hours", type=int, default=4)
    parser.add_argument("--kcxx-tolerance-minutes", type=float, default=4.0)
    parser.add_argument("--ktyx-max-age-minutes", type=float, default=8.0)
    parser.add_argument("--archive-attempts", type=int, default=6)
    parser.add_argument("--archive-delay-seconds", type=int, default=20)
    # KTYX is the synchronized companion radar selected by process_live_event.
    # Keep the companion selector explicit in the publisher contract for validation.
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

    # Only select scans that the event processor can still resolve from the
    # same near-real-time archive window. Older entries can remain in the
    # discovery list after their processing window has expired; feeding one
    # of those to process_live_event can fail the entire cycle before newer
    # scans are reached. Let old gaps age out instead of blocking the feed.
    all_recent = find_recent_volumes(
        s3, "KCXX", since=None, lookback_hours=args.lookback_hours
    )
    processing_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    candidates = [
        item for item in all_recent
        if Path(item[0]).name not in processed_sources
        and item[1] > (previous or datetime.min.replace(tzinfo=timezone.utc))
        and item[1] >= processing_cutoff
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

    processed = 0
    skipped = 0
    for index, (_, scan_time) in enumerate(candidates, start=1):
        stamp = scan_time.isoformat().replace("+00:00", "Z")
        source_available = any(
            abs((when - scan_time).total_seconds()) <= args.kcxx_tolerance_minutes * 60
            for _, when in find_recent_volumes(
                s3, "KCXX", since=scan_time - timedelta(minutes=args.kcxx_tolerance_minutes),
                lookback_hours=max(2, args.lookback_hours)
            )
        )
        raw_matches = list((args.raw_root / "KCXX").glob(f"*{scan_time.strftime('%Y%m%d_%H%M')}*"))
        if not source_available and not raw_matches:
            skipped += 1
            print(f"=== BACKFILL {index}/{len(candidates)}: KCXX {stamp} ===")
            print("KCXX archive source is not currently resolvable; skipping this scan so one archive gap cannot block newer scans.")
            continue
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
        try:
            subprocess.run(cmd, check=True)
            processed += 1
        except subprocess.CalledProcessError as exc:
            skipped += 1
            print(f"KCXX {stamp} failed with exit code {exc.returncode}; continuing to the next scan.")
            continue

    print(f"LIVE RADAR BACKFILL COMPLETE: processed={processed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
