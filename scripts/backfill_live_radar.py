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


def published_time(live_root: Path) -> datetime | None:
    event = live_root / "event_cycle.json"
    if event.exists():
        try:
            payload = json.loads(event.read_text(encoding="utf-8"))
            return parse_time((payload.get("kcxx") or {}).get("scan_time_utc"))
        except Exception:
            pass
    return None


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
    candidates = find_recent_volumes(
        s3, "KCXX", since=previous, lookback_hours=args.lookback_hours
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
