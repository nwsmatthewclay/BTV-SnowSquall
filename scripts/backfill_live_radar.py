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

from acquisition.radar_watcher import download_volume, find_recent_volumes, make_s3_client


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
    parser.add_argument("--max-cycles", type=int, default=18)
    parser.add_argument("--lookback-hours", type=int, default=3)
    parser.add_argument("--kcxx-tolerance-minutes", type=float, default=4.0)
    parser.add_argument("--ktyx-max-age-minutes", type=float, default=8.0)
    parser.add_argument("--archive-attempts", type=int, default=6)
    parser.add_argument("--archive-delay-seconds", type=int, default=20)
    # KTYX is the synchronized companion radar selected by process_live_event.
    # Keep the companion selector explicit in the publisher contract for validation.
    args = parser.parse_args()

    previous = published_time(args.live_root)
    s3 = make_s3_client()

    # Repair the radar-history archive by comparing recent KCXX scans with
    # actual retained frames, not with the latest processed-source watermark.
    # The newest scan can be healthy while earlier timeline frames are missing.
    # Replaying an already-processed scan is safe here: process_live_volume
    # skips duplicate/out-of-order tracker updates, while process_live_event
    # still rebuilds the matching radar image and archives the missing frame.
    all_recent = find_recent_volumes(
        s3, "KCXX", since=None, lookback_hours=args.lookback_hours
    )
    ktyx_recent = find_recent_volumes(
        s3, "KTYX", since=None, lookback_hours=args.lookback_hours
    )
    manifest_path = args.live_root / "radar_history" / "manifest.json"
    frame_times = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            frame_times = [
                parsed for frame in manifest.get("frames", [])
                if (parsed := parse_time(frame.get("timestamp"))) is not None
            ]
        except (OSError, json.JSONDecodeError, TypeError):
            frame_times = []
    # The browser archive retains roughly the last 100 minutes. Keep a small
    # margin and rebuild any scan not represented by a frame within 3 minutes.
    processing_cutoff = datetime.now(timezone.utc) - timedelta(minutes=100)
    candidates = [
        item for item in all_recent
        if item[1] >= processing_cutoff
        and not any(abs((frame_time - item[1]).total_seconds()) <= 180 for frame_time in frame_times)
    ]

    print(
        "Latest published watermark:",
        previous.isoformat() if previous else "none",
        "| recent KCXX volumes:",
        len(all_recent),
        "| retained frames:",
        len(frame_times),
        "| radar-history gaps to repair:",
        len(candidates),
    )

    if not candidates:
        print("Radar history is caught up; no missing recent frames found.")
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
    for index, (kcxx_key, scan_time) in enumerate(candidates, start=1):
        stamp = scan_time.isoformat().replace("+00:00", "Z")
        print(f"=== BACKFILL {index}/{len(candidates)}: KCXX {stamp} ===")

        # Resolve and cache the exact KCXX source now. This turns the expensive
        # archive lookup into a bounded operation and lets process_live_event
        # operate entirely from local files.
        try:
            kcxx_local = download_volume(s3, "KCXX", kcxx_key, scan_time)
            # Select the newest KTYX volume at/before KCXX within the sync window
            # from the already-discovered archive list; never issue another S3
            # listing just to pair the companion radar.
            eligible_ktyx = [
                item for item in ktyx_recent
                if item[1] <= scan_time
                and (scan_time - item[1]).total_seconds() / 60.0 <= args.ktyx_max_age_minutes
            ]
            if eligible_ktyx:
                ktyx_key, ktyx_time = max(eligible_ktyx, key=lambda item: item[1])
                download_volume(s3, "KTYX", ktyx_key, ktyx_time)
                print(f"Cached KTYX companion: {ktyx_key} {ktyx_time.isoformat()}")
            else:
                print("No synchronized KTYX companion in cached archive window; KCXX-only cycle.")
        except Exception as exc:
            skipped += 1
            print(f"Could not cache radar sources for {stamp}: {exc}; continuing.")
            continue
        cmd = [
            sys.executable,
            "scripts/process_live_event.py",
            "--scan-time", stamp,
            "--archive-only",
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
