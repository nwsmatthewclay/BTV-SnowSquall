"""Download historical NEXRAD Level-II volumes for case reconstruction.

The NOAA/Unidata Level-II archive is public. This module deliberately separates
manifest generation from downloading so a case can be reconstructed reproducibly.

Example:
    python acquisition/historical_level2.py --manifest data/manifests/banacos_radar_windows.csv --output data/raw/level2 --case-id BTV20060224
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
FILENAME_RE = re.compile(r"^(?P<radar>K[A-Z0-9]{3})(?P<stamp>\d{8}_\d{6})_.*$")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def s3_client():
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED),
    )


def list_volume_keys(client, radar: str, day: datetime) -> list[str]:
    prefix = f"{day:%Y/%m/%d}/{radar}/"
    paginator = client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Historical Level-II objects can be stored without a filename extension.
            # The timestamp parser below is the authoritative filter.
            if Path(key).name:
                keys.append(key)
    return keys


def key_time(key: str) -> datetime | None:
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="data/raw/level2")
    parser.add_argument("--case-id")
    args = parser.parse_args()

    with open(args.manifest, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if args.case_id:
        rows = [r for r in rows if r["case_id"] == args.case_id]

    client = s3_client()
    total = 0
    for row in rows:
        start = parse_utc(row["window_start_utc"])
        end = parse_utc(row["window_end_utc"])
        n = download_window(client, row["radar_site"], start, end, Path(args.output))
        total += n
        print(f"{row['case_id']} {row['radar_site']}: downloaded {n} volumes")

    print(f"Downloaded {total} new Level-II volumes.")


if __name__ == "__main__":
    main()
