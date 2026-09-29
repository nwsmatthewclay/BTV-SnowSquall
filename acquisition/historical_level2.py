"""Download historical NEXRAD Level-II volumes for case reconstruction.

The NOAA/Unidata Level-II archive is public. This module deliberately separates
manifest generation from downloading so a case can be reconstructed reproducibly.
"""
from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.client import Config

BUCKET = "unidata-nexrad-level2"
FILENAME_RE = re.compile(r"^(?P<radar>K[A-Z0-9]{3})(?P<stamp>\d{8}_\d{6})(?:_.*|\.gz)$")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def s3_client():
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED),
    )


def s3_listing_client():
    """Create a bounded-timeout client for archive preflight/list operations."""
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=20,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


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


def download_window(client, radar: str, start: datetime, end: datetime, output: Path) -> int:
    downloaded = 0
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day.date() <= end.date():
        for key in list_volume_keys(client, radar, day):
            t = key_time(key)
            if t is None or t < start or t > end:
                continue
            target = output / radar / f"{t:%Y%m%d}" / Path(key).name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                continue
            client.download_file(BUCKET, key, str(target))
            downloaded += 1
        day = day.fromtimestamp(day.timestamp() + 86400, tz=timezone.utc)
    return downloaded


def filter_manifest_rows(rows, case_id=None, radar_site=None):
    if case_id:
        rows = [r for r in rows if case_id in {r.get('case_id'), r.get('window_id'), r.get('null_id')}]
    if radar_site:
        rows = [r for r in rows if r.get('radar_site') == radar_site]
    return rows

def row_identifier(row: dict) -> str:
    return (
        row.get("case_id")
        or row.get("window_id")
        or row.get("null_id")
        or "UNKNOWN"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="data/raw/level2")
    parser.add_argument("--case-id")
    parser.add_argument("--radar-site", choices=("KCXX", "KTYX"))
    args = parser.parse_args()

    with open(args.manifest, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    rows = filter_manifest_rows(rows, case_id=args.case_id, radar_site=args.radar_site)

    client = s3_client()
    total = 0
    for row in rows:
        start = parse_utc(row["window_start_utc"])
        end = parse_utc(row["window_end_utc"])
        n = download_window(client, row["radar_site"], start, end, Path(args.output))
        total += n
        print(f"{row_identifier(row)} {row['radar_site']}: downloaded {n} volumes")

    print(f"Downloaded {total} new Level-II volumes.")


if __name__ == "__main__":
    main()
