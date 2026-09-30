#!/usr/bin/env python3
"""Download historical KCXX/KTYX Level-II volumes around a labeled case."""
from __future__ import annotations

import argparse
import csv
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

BUCKET = "unidata-nexrad-level2"
REGION = "us-east-1"
RADARS = ("KCXX", "KTYX")
VOL_RE = re.compile(
    r"(?P<radar>[A-Z0-9]{4})(?P<date>\d{8})[_-]?(?P<time>\d{6})",
    re.IGNORECASE,
)
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "historical" / "case_manifest.csv"
RAW_ROOT = ROOT / "data" / "raw"
META_ROOT = ROOT / "data" / "derived"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--case-id", required=True)
    p.add_argument("--pre-min", type=int, default=60)
    p.add_argument("--post-min", type=int, default=90)
    p.add_argument("--radars", nargs="+", choices=RADARS, default=list(RADARS))
    return p.parse_args()


def s3_client():
    return boto3.client(
        "s3",
        region_name=REGION,
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=20,
            read_timeout=120,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


def read_case(case_id: str) -> dict[str, str]:
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["case_id"] == case_id:
                return row
    raise SystemExit(f"Unknown case_id: {case_id}")


def event_time(row: dict[str, str]) -> datetime:
    return datetime.strptime(
        f'{row["event_date"]} {row["event_time_utc"]}',
        "%Y-%m-%d %H:%M",
    ).replace(tzinfo=timezone.utc)


def parse_volume_time(key: str, radar: str) -> datetime | None:
    m = VOL_RE.search(Path(key).name)
    if not m or m.group("radar").upper() != radar:
        return None
    return datetime.strptime(
        m.group("date") + m.group("time"),
        "%Y%m%d%H%M%S",
    ).replace(tzinfo=timezone.utc)


def list_hour(s3, radar: str, when: datetime) -> list[dict]:
    prefix = (
        f"{when:%Y}/{when:%m}/{when:%d}/{radar}/"
        f"{radar}{when:%Y%m%d_%H}"
    )
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return response.get("Contents", [])


def main() -> None:
    args = parse_args()
    case = read_case(args.case_id)
    start = event_time(case) - timedelta(minutes=args.pre_min)
    end = event_time(case) + timedelta(minutes=args.post_min)

    META_ROOT.mkdir(parents=True, exist_ok=True)
    inventory_path = META_ROOT / f"{args.case_id}_radar_inventory.csv"
    s3 = s3_client()

    inventory: list[dict[str, str]] = []
    seen: set[str] = set()
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor <= end:
        for radar in args.radars:
            for item in list_hour(s3, radar, cursor):
                key = item["Key"]
                if key in seen:
                    continue
                vt = parse_volume_time(key, radar)
                if vt is None or vt < start or vt > end:
                    continue
                seen.add(key)
                inventory.append({
                    "case_id": args.case_id,
                    "radar": radar,
                    "volume_time_utc": vt.isoformat().replace("+00:00", "Z"),
                    "s3_key": key,
                    "size_bytes": str(item.get("Size", "")),
                })
        cursor += timedelta(hours=1)

    inventory.sort(key=lambda x: (x["volume_time_utc"], x["radar"]))
    with inventory_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["case_id", "radar", "volume_time_utc", "s3_key", "size_bytes"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(inventory)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s UTC | %(levelname)s | %(message)s")
    logging.info("Case %s: discovered %d Level-II volumes", args.case_id, len(inventory))

    downloaded = 0
    for item in inventory:
        radar = item["radar"]
        local_dir = RAW_ROOT / radar / args.case_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / Path(item["s3_key"]).name
        if local_path.exists() and local_path.stat().st_size > 0:
            continue

        temp = local_path.with_suffix(local_path.suffix + ".part")
        try:
            logging.info("Downloading %s -> %s", item["s3_key"], local_path)
            if temp.exists():
                temp.unlink()
            s3.download_file(BUCKET, item["s3_key"], str(temp))
            if temp.stat().st_size == 0:
                raise IOError("empty download")
            temp.replace(local_path)
            downloaded += 1
        except Exception:
            if temp.exists():
                temp.unlink()
            logging.exception("Failed download: %s", item["s3_key"])
            raise
        time.sleep(0.05)

    logging.info("Downloaded %d new volumes; inventory=%s", downloaded, inventory_path)


if __name__ == "__main__":
    main()
