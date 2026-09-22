"""
BTV Snow Squall Project - real-time NEXRAD Level II acquisition.

Phase 1:
    Watch the public NOAA/Unidata NEXRAD Level II archive for one radar,
    download each newly available completed volume, and log acquisition
    latency.

This is intentionally independent of the later snow-squall algorithm.
The acquisition layer can later be switched from polling to SNS/SQS
without changing the downstream processing interface.
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config


BUCKET = "unidata-nexrad-level2"
REGION = "us-east-1"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
LOG_ROOT = PROJECT_ROOT / "logs"

RADARS = ("KCXX", "KTYX")
POLL_SECONDS = 10
LOOKBACK_HOURS = 2

# NEXRAD archive filenames normally contain:
#   RADAR + YYYYMMDD_HHMMSS...
# Keep this regex broad enough for naming-version changes.
VOLUME_TIME_RE = re.compile(
    r"(?P<radar>[A-Z0-9]{4})(?P<date>\d{8})[_-]?(?P<time>\d{6})",
    re.IGNORECASE,
)


def setup_logging(radar: str) -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s UTC | %(levelname)s | %(message)s"
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(LOG_ROOT / f"{radar.lower()}_watcher.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_volume_time(key: str, radar: str) -> datetime | None:
    match = VOLUME_TIME_RE.search(Path(key).name)
    if not match:
        return None

    if match.group("radar").upper() != radar.upper():
        return None

    try:
        return datetime.strptime(
            f"{match.group('date')}{match.group('time')}",
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def make_s3_client():
    # NOAA/Unidata's public bucket does not require AWS credentials.
    return boto3.client(
        "s3",
        region_name=REGION,
        config=Config(signature_version=UNSIGNED),
    )


def archive_prefix(radar: str, when: datetime) -> str:
    return (
        f"{when:%Y}/{when:%m}/{when:%d}/"
        f"{radar}/{radar}{when:%Y%m%d_%H}"
    )


def find_newest_volume(s3, radar: str) -> tuple[str, datetime] | None:
    """
    Search the current and previous hour for the newest completed volume.
    The archive bucket contains assembled volume files, so we don't need
    to reconstruct chunks in this first test.
    """
    now = utc_now()

    candidates: list[tuple[str, datetime]] = []

    for hour_offset in range(LOOKBACK_HOURS):
        when = now.replace(minute=0, second=0, microsecond=0)
        when = when.timestamp() - (hour_offset * 3600)
        hour_dt = datetime.fromtimestamp(when, tz=timezone.utc)

        prefix = archive_prefix(radar, hour_dt)

        response = s3.list_objects_v2(
            Bucket=BUCKET,
            Prefix=prefix,
        )

        for item in response.get("Contents", []):
            key = item["Key"]
            volume_time = parse_volume_time(key, radar)

            if volume_time is not None:
                candidates.append((key, volume_time))

    if not candidates:
        return None

    return max(candidates, key=lambda x: x[1])


def download_volume(s3, radar: str, key: str, volume_time: datetime) -> Path:
    radar_dir = RAW_ROOT / radar
    radar_dir.mkdir(parents=True, exist_ok=True)

    local_path = radar_dir / Path(key).name

    if not local_path.exists():
        logging.info("Downloading %s -> %s", key, local_path)
        s3.download_file(BUCKET, key, str(local_path))
    else:
        logging.info("Already have %s", local_path.name)

    return local_path


def log_latency(radar: str, volume_time: datetime, downloaded_at: datetime) -> None:
    age = downloaded_at - volume_time
    logging.info(
        "%s volume=%s | acquired=%s | age=%s",
        radar,
        volume_time.isoformat(),
        downloaded_at.isoformat(),
        age,
    )


def run(radar: str, poll_seconds: int) -> None:
    setup_logging(radar)

    logging.info("=" * 72)
    logging.info("BTV SNOW SQUALL - %s REAL-TIME ACQUISITION TEST", radar)
    logging.info("Bucket: %s", BUCKET)
    logging.info("Poll interval: %s seconds", poll_seconds)
    logging.info("Started: %s", utc_now().isoformat())
    logging.info("=" * 72)

    s3 = make_s3_client()
    last_key: str | None = None

    while True:
        try:
            newest = find_newest_volume(s3, radar)

            if newest is None:
                logging.warning("No recent %s volumes found.", radar)
            else:
                key, volume_time = newest

                if key != last_key:
                    discovered_at = utc_now()

                    logging.info(
                        "New %s volume found: %s | radar time=%s",
                        radar,
                        key,
                        volume_time.isoformat(),
                    )

                    path = download_volume(
                        s3,
                        radar,
                        key,
                        volume_time,
                    )

                    completed_at = utc_now()
                    log_latency(radar, volume_time, completed_at)

                    logging.info(
                        "Local file ready: %s | download_time=%s",
                        path,
                        completed_at - discovered_at,
                    )

                    last_key = key

            time.sleep(poll_seconds)

        except KeyboardInterrupt:
            logging.info("Stopped by user.")
            break

        except Exception:
            logging.exception("Watcher error; retrying after 5 seconds.")
            time.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch one BTV-area NEXRAD Level II radar in near real time."
    )
    parser.add_argument(
        "--radar",
        required=True,
        choices=RADARS,
        help="Radar site to watch.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=POLL_SECONDS,
        help=f"Polling interval in seconds (default: {POLL_SECONDS}).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.radar, max(2, args.poll_seconds))
