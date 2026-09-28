"""Acquire time-matched RAP analysis data for radar-object environmental features.

The selector is deliberately retrospective: for a radar scan at time T it only
accepts a RAP analysis whose valid time is <= T. A future RAP analysis is never
allowed into an object record.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import requests


BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rap/prod"
FILENAME_TEMPLATE = "rap.t{hour:02d}z.awp130bgrbf00.grib2"
DATE_RE = re.compile(r"rap\.(\d{8})$")


@dataclass(frozen=True)
class RapMatch:
    valid_time: datetime
    url: str
    local_path: Path
    age_minutes: float


def rap_analysis_url(valid_time: datetime) -> str:
    valid_time = valid_time.astimezone(timezone.utc)
    date_dir = valid_time.strftime("%Y%m%d")
    filename = FILENAME_TEMPLATE.format(hour=valid_time.hour)
    return f"{BASE_URL}/rap.{date_dir}/{filename}"


def find_latest_analysis(
    radar_time: datetime,
    max_age_minutes: int = 180,
) -> RapMatch | None:
    """Return the newest hourly RAP analysis at or before radar_time."""
    radar_time = radar_time.astimezone(timezone.utc).replace(second=0, microsecond=0)

    for offset in range(0, max_age_minutes + 60, 60):
        valid = radar_time - timedelta(minutes=offset)
        valid = valid.replace(minute=0)
        url = rap_analysis_url(valid)

        response = requests.head(url, timeout=20, allow_redirects=True)
        if response.status_code == 200:
            age = (radar_time - valid).total_seconds() / 60.0
            if age <= max_age_minutes:
                return RapMatch(valid, url, Path(url.rsplit("/", 1)[-1]), age)

    return None


def download_analysis(match: RapMatch, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / match.local_path.name
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    with requests.get(match.url, stream=True, timeout=(20, 120)) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)

    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise IOError(f"Empty RAP download: {match.url}")

    partial.replace(destination)
    return destination


def acquire_for_radar_time(
    radar_time: datetime,
    output_dir: Path = Path("data/raw/RAP"),
    max_age_minutes: int = 180,
) -> tuple[RapMatch, Path] | None:
    match = find_latest_analysis(radar_time, max_age_minutes=max_age_minutes)
    if match is None:
        return None
    return match, download_analysis(match, output_dir)
