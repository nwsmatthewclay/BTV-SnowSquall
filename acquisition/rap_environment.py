"""Acquire time-matched RAP analysis data for radar-object environmental features.

The selector is deliberately retrospective: for a radar scan at time T it only
accepts a RAP analysis whose valid time is <= T. A future RAP analysis is never
allowed into an object record.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
import random
import re
import time
import requests


BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rap/prod"
NCEI_BASE = "https://www.ncei.noaa.gov/thredds/fileServer"
NCEI_DATASETS = ("model-rap130anl", "model-rap130anl-old")
FILENAME_TEMPLATE = "rap.t{hour:02d}z.awp130pgrbf00.grib2"
NCEI_FILENAME_TEMPLATE = "rap_130_{date}_{hour:02d}00_000.grb2"
DATE_RE = re.compile(r"rap\.(\d{8})$")
NOMADS_PREFERRED_AGE_DAYS = 7


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


def ncei_rap_analysis_urls(valid_time: datetime):
    valid_time = valid_time.astimezone(timezone.utc)
    stamp = valid_time.strftime("%Y%m%d")
    month = valid_time.strftime("%Y%m")
    filename = NCEI_FILENAME_TEMPLATE.format(date=stamp, hour=valid_time.hour)
    for dataset in NCEI_DATASETS:
        yield f"{NCEI_BASE}/{dataset}/{month}/{stamp}/{filename}"


@lru_cache(maxsize=2048)
def _url_exists(url: str) -> bool:
    """Probe a remote model file with a tiny ranged GET."""
    for attempt, delay in enumerate((0, 1, 3), start=1):
        if delay:
            time.sleep(delay + random.uniform(0.0, 0.5))
        try:
            response = requests.get(
                url,
                stream=True,
                timeout=(8, 20),
                allow_redirects=True,
                headers={"Range": "bytes=0-0"},
            )
            status = response.status_code
            response.close()
            if status in (200, 206):
                return True
            if status in (404, 410):
                return False
            if status not in (429, 500, 502, 503, 504):
                return False
        except requests.RequestException:
            if attempt == 3:
                return False
    return False


def _ncei_match(valid_time: datetime, radar_time: datetime, max_age_minutes: int):
    age = (radar_time - valid_time).total_seconds() / 60.0
    if age < 0 or age > max_age_minutes:
        return None
    for url in ncei_rap_analysis_urls(valid_time):
        if _url_exists(url):
            return RapMatch(
                valid_time,
                url,
                Path(url.rsplit("/", 1)[-1]),
                age,
            )
    return None


def find_latest_analysis(
    radar_time: datetime,
    max_age_minutes: int = 180,
) -> RapMatch | None:
    """Return the newest hourly RAP analysis at or before radar_time."""
    radar_time = radar_time.astimezone(timezone.utc).replace(second=0, microsecond=0)

    historical_cutoff = datetime.now(timezone.utc) - timedelta(days=NOMADS_PREFERRED_AGE_DAYS)

    for offset in range(0, max_age_minutes + 60, 60):
        valid = (radar_time - timedelta(minutes=offset)).replace(minute=0)

        if valid >= historical_cutoff:
            url = rap_analysis_url(valid)
            if _url_exists(url):
                age = (radar_time - valid).total_seconds() / 60.0
                return RapMatch(valid, url, Path(url.rsplit("/", 1)[-1]), age)

            match = _ncei_match(valid, radar_time, max_age_minutes)
            if match is not None:
                return match
        else:
            match = _ncei_match(valid, radar_time, max_age_minutes)
            if match is not None:
                return match

            url = rap_analysis_url(valid)
            if _url_exists(url):
                age = (radar_time - valid).total_seconds() / 60.0
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
