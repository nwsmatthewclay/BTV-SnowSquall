#!/usr/bin/env python3
"""Find the newest public KCXX Level-II volume that has not been published.

The archive is the public Unidata NEXRAD Level-II S3 bucket, so this requires
no AWS credentials. The live-data branch is used as the durable watermark.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from acquisition.radar_watcher import find_newest_volume, make_s3_client


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


def last_published_time(live_root: Path) -> datetime | None:
    event_path = live_root / "event_cycle.json"
    if event_path.exists():
        try:
            data = json.loads(event_path.read_text(encoding="utf-8"))
            value = data.get("kcxx", {}).get("scan_time_utc")
            parsed = parse_time(value)
            if parsed:
                return parsed
        except Exception:
            pass

    # Backward-compatible fallback while the event-cycle watermark is first
    # established.
    radar_path = live_root / "radar_mosaic.json"
    if radar_path.exists():
        try:
            data = json.loads(radar_path.read_text(encoding="utf-8"))
            for source in data.get("sources", []):
                if source.get("radar") == "KCXX":
                    parsed = parse_time(source.get("scan_time_utc"))
                    if parsed:
                        return parsed
        except Exception:
            pass

    return None


def main() -> int:
    live_root = Path(os.environ.get("LIVE_ROOT", "viewer/data/live"))
    s3 = make_s3_client()
    newest = find_newest_volume(s3, "KCXX")

    if newest is None:
        print("No KCXX volume found.")
        return 2

    key, scan_time = newest
    previous = last_published_time(live_root)

    print(f"Newest KCXX: {key} {scan_time.isoformat()}")
    print(f"Previously published KCXX: {previous.isoformat() if previous else 'none'}")

    if previous is not None and scan_time <= previous:
        print("No new KCXX scan.")
        return 0

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"new_scan=true\n")
            fh.write(f"scan_time={scan_time.isoformat().replace('+00:00', 'Z')}\n")
            fh.write(f"source_key={key}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
