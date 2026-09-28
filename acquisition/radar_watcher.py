"""
BTV Snow Squall Project - resilient real-time NEXRAD Level II acquisition.

The watcher is intentionally idempotent: a volume is only downloaded when the
local file is absent or empty. A future restart may rediscover the newest
archive object, but the existing local file is reused rather than downloaded
again.
"""
from __future__ import annotations

import argparse
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
LOG_ROOT = PROJECT_ROOT / "logs"

RADARS = ("KCXX", "KTYX")
POLL_SECONDS = 10
LOOKBACK_HOURS = 2
DOWNLOAD_TIMEOUT = 60
MAX_RETRIES = 3

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
    if not match or match.group("radar").upper() != radar.upper():
        return None

    try:
        return datetime.strptime(
            f"{match.group('date')}{match.group('time')}",
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def make_s3_client():
    return boto3.client(
        "s3",
        region_name=REGION,
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=15,
            read_timeout=DOWNLOAD_TIMEOUT,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def archive_prefix(radar: str, when: datetime) -> str:
    return (
        f"{when:%Y}/{when:%m}/{when:%d}/"
        f"{radar}/{radar}{when:%Y%m%d_%H}"
    )


def find_newest_volume(s3, radar: str) -> tuple[str, datetime] | None:
    now = utc_now()
    candidates: list[tuple[str, datetime]] = []

    for hour_offset in range(LOOKBACK_HOURS):
        hour_dt = now.replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=hour_offset
        )
        response = s3.list_objects_v2(
            Bucket=BUCKET,
            Prefix=archive_prefix(radar, hour_dt),
        )

        for item in response.get("Contents", []):
            volume_time = parse_volume_time(item["Key"], radar)
            if volume_time is not None:
                candidates.append((item["Key"], volume_time))

    return max(candidates, key=lambda x: x[1]) if candidates else None


def download_volume(
    s3, radar: str, key: str, volume_time: datetime
) -> Path:
    radar_dir = RAW_ROOT / radar
    radar_dir.mkdir(parents=True, exist_ok=True)
    local_path = radar_dir / Path(key).name

    if local_path.exists() and local_path.stat().st_size > 0:
        logging.info(
            "Already have %s (%d bytes); skipping download.",
            local_path.name,
            local_path.stat().st_size,
        )
        return local_path

    for attempt in range(1, MAX_RETRIES + 1):
        temp_path = local_path.with_suffix(local_path.suffix + ".part")
        try:
            logging.info(
                "Downloading %s -> %s (attempt %d/%d)",
                key,
                local_path,
                attempt,
                MAX_RETRIES,
            )

            if temp_path.exists():
                temp_path.unlink()

            s3.download_file(BUCKET, key, str(temp_path))

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise IOError("empty download")

            temp_path.replace(local_path)
            return local_path

        except Exception:
            if temp_path.exists():
                temp_path.unlink()

            logging.exception(
                "Download failed for %s on attempt %d/%d",
                key,
                attempt,
                MAX_RETRIES,
            )
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
            else:
                raise

    raise RuntimeError("unreachable")


def run(radar: str, poll_seconds: int, max_polls: int | None = None) -> None:
    setup_logging(radar)

    logging.info("=" * 72)
    logging.info("BTV SNOW SQUALL - %s REAL-TIME ACQUISITION TEST", radar)
    logging.info("Bucket: %s", BUCKET)
    logging.info("Poll interval: %s seconds", poll_seconds)
    if max_polls is not None:
        logging.info("Maximum polls: %s", max_polls)
    logging.info("Started: %s", utc_now().isoformat())
    logging.info("=" * 72)

    s3 = make_s3_client()
    last_key: str | None = None

    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1

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
                        s3, radar, key, volume_time
                    )

                    completed_at = utc_now()
                    logging.info(
                        "%s volume=%s | acquired=%s | age=%s",
                        radar,
                        volume_time.isoformat(),
                        completed_at.isoformat(),
                        completed_at - volume_time,
                    )
                    logging.info(
                        "Local file ready: %s | download_time=%s",
                        path,
                        completed_at - discovered_at,
                    )
                    last_key = key
                else:
                    logging.info(
                        "No newer %s volume; latest is still %s.",
                        radar,
                        key,
                    )

            if max_polls is not None and polls >= max_polls:
                break

            time.sleep(poll_seconds)

        except KeyboardInterrupt:
            logging.info("Stopped by user.")
            break

        except Exception:
            logging.exception(
                "Watcher error; retrying after 5 seconds."
            )
            time.sleep(5)

    logging.info("Watcher test finished after %d poll(s).", polls)


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
    parser.add_argument(
        "--max-polls",
        type=int,
        default=None,
        help="Stop after this many polls; useful for CI tests.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        args.radar,
        max(2, args.poll_seconds),
        max_polls=args.max_polls,
    )
