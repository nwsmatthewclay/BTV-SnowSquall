"""Download historical NEXRAD Level-II volumes for case reconstruction.

The NOAA/Unidata Level-II archive is public. This module deliberately separates
manifest generation from downloading so a case can be reconstructed reproducibly.

The downloader batches overlapping manifest windows by radar/day and downloads
unique volumes concurrently. This avoids repeatedly listing the same S3 prefix
for overlapping cases and removes the previous one-volume-at-a-time bottleneck.
"""
from __future__ import annotations

import argparse
import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore import BotoCoreError
from botocore import UNSIGNED
from botocore.client import Config

BUCKET = "unidata-nexrad-level2"
FILENAME_RE = re.compile(r"^(?P<radar>K[A-Z0-9]{3})(?P<stamp>\d{8}_\d{6})(?:_.*|\.gz)$")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def s3_client(max_pool_connections: int = 16):
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 4, "mode": "standard"},
            max_pool_connections=max_pool_connections,
        ),
    )


def s3_listing_client():
    """Create a bounded-timeout client for archive preflight/list operations."""
    return s3_client(max_pool_connections=16)


def list_volume_keys(client, radar: str, day: datetime) -> list[str]:
    prefix = f"{day:%Y/%m/%d}/{radar}/"
    paginator = client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if Path(key).name:
                keys.append(key)
    return keys


def key_time(key: str) -> datetime | None:
    if Path(key).name.endswith("_MDM"):
        return None
    match = FILENAME_RE.match(Path(key).name)
    if not match:
        return None
    return datetime.strptime(match.group("stamp"), "%Y%m%d_%H%M%S").replace(
        tzinfo=timezone.utc
    )


def _day_keys(start: datetime, end: datetime):
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    last = end.replace(hour=0, minute=0, second=0, microsecond=0)
    while day.date() <= last.date():
        yield day
        day += timedelta(days=1)


def _prepare_downloads(client, rows):
    """Resolve all manifest windows against one cached radar/day archive listing."""
    requested = []
    listing_tasks = set()

    for row in rows:
        start = parse_utc(row["window_start_utc"])
        end = parse_utc(row["window_end_utc"])
        radar = row["radar_site"]
        requested.append((row, radar, start, end))
        for day in _day_keys(start, end):
            listing_tasks.add((radar, day))

    listings = {}
    # Listing is network-bound too, so do it concurrently.
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(listing_tasks)))) as pool:
        futures = {
            pool.submit(list_volume_keys, client, radar, day): (radar, day)
            for radar, day in sorted(listing_tasks, key=lambda x: (x[0], x[1]))
        }
        for future in as_completed(futures):
            radar, day = futures[future]
            listings[(radar, day.date())] = future.result()

    targets = {}
    row_matches = {}
    for row, radar, start, end in requested:
        row_id = row_identifier(row)
        matched = 0
        for day in _day_keys(start, end):
            for key in listings[(radar, day.date())]:
                timestamp = key_time(key)
                if timestamp is None or timestamp < start or timestamp > end:
                    continue
                matched += 1
                targets.setdefault((radar, key), (timestamp, row_id))
        row_matches[row_id] = matched

    return targets, row_matches, len(listing_tasks)


def filter_manifest_rows(rows, case_id=None, radar_site=None):
    if case_id:
        rows = [
            r for r in rows
            if case_id in {r.get("case_id"), r.get("window_id"), r.get("null_id")}
        ]
    if radar_site:
        rows = [r for r in rows if r.get("radar_site") == radar_site]
    return rows


def row_identifier(row: dict) -> str:
    return (
        row.get("case_id")
        or row.get("window_id")
        or row.get("null_id")
        or "UNKNOWN"
    )


def _download_one(client, radar: str, key: str, timestamp: datetime, output: Path) -> int:
    target = output / radar / f"{timestamp:%Y%m%d}" / Path(key).name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return 0
    client.download_file(BUCKET, key, str(target))
    return 1


def download_manifest(rows, output: Path, workers: int = 8) -> int:
    if not rows:
        return 0

    workers = max(1, min(int(workers), 16))
    client = s3_client(max_pool_connections=max(16, workers * 2))
    targets, row_matches, listing_count = _prepare_downloads(client, rows)

    print(
        f"Prepared {len(rows)} manifest rows across {listing_count} unique "
        f"radar/day archive listings and {len(targets)} unique radar volumes."
    )
    for row_id, matched in row_matches.items():
        print(f"{row_id}: {matched} archive volumes in requested windows")

    downloaded = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _download_one,
                client,
                radar,
                key,
                timestamp,
                output,
            ): (radar, key)
            for (radar, key), (timestamp, _) in targets.items()
        }
        for future in as_completed(futures):
            radar, key = futures[future]
            try:
                downloaded += future.result()
            except (BotoCoreError, OSError, Exception):
                failed += 1
                raise

    print(
        f"Downloaded {downloaded} new Level-II volumes; "
        f"{len(targets) - downloaded} already existed; failed={failed}."
    )
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="data/raw/level2")
    parser.add_argument("--case-id")
    parser.add_argument("--radar-site", choices=("KCXX", "KTYX"))
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent Level-II downloads (capped at 16).",
    )
    args = parser.parse_args()

    with open(args.manifest, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    rows = filter_manifest_rows(rows, case_id=args.case_id, radar_site=args.radar_site)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    downloaded = download_manifest(rows, output, workers=args.workers)

    print(f"Downloaded {downloaded} new Level-II volumes.")


if __name__ == "__main__":
    main()
