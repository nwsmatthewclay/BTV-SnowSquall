"""Acquire time-matched historical NARR-A analyses for early radar cases.

NARR is used only for radar times before the RUC 13-km analysis archive begins.
It provides a leakage-safe, 3-hourly historical analysis and is explicitly
recorded as a different environment source in the dataset.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

BASE = "https://www.ncei.noaa.gov/thredds/fileServer"
DATASET = "model-narr-a-files"


@dataclass(frozen=True)
class NarrMatch:
    valid_time: datetime
    url: str
    local_path: Path
    age_minutes: float


def _floor_3h(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return dt.replace(hour=(dt.hour // 3) * 3)


def narr_analysis_url(valid_time: datetime) -> str:
    valid_time = _floor_3h(valid_time)
    stamp = valid_time.strftime("%Y%m%d")
    month = valid_time.strftime("%Y%m")
    filename = f"narr-a_221_{stamp}_{valid_time:%H}00_000.grb"
    return f"{BASE}/{DATASET}/{month}/{stamp}/{filename}"


def _exists(url: str) -> bool:
    """Use a short GET probe because some NOAA file-server endpoints do not
    reliably implement HEAD for historical files."""
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(8, 12),
            allow_redirects=True,
            headers={"Range": "bytes=0-0"},
        ) as response:
            return response.status_code in (200, 206)
    except requests.RequestException:
        return False


def find_latest_analysis(radar_time: datetime, max_age_minutes: int = 360):
    radar_time = radar_time.astimezone(timezone.utc)
    latest = _floor_3h(radar_time)
    attempts = max(0, max_age_minutes // 180)

    for index in range(attempts + 1):
        valid = latest - timedelta(minutes=index * 180)
        age = (radar_time - valid).total_seconds() / 60.0
        if age < 0 or age > max_age_minutes:
            continue

        url = narr_analysis_url(valid)
        if _exists(url):
            return NarrMatch(
                valid,
                url,
                Path(url.rsplit("/", 1)[-1]),
                age,
            )
    return None


def download_analysis(match: NarrMatch, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / match.local_path.name
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with requests.get(match.url, stream=True, timeout=(15, 180)) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise IOError(f"Empty NARR download: {match.url}")

    partial.replace(destination)
    return destination


def acquire_for_radar_time(
    radar_time: datetime,
    output_dir: Path = Path("data/raw/NARR"),
    max_age_minutes: int = 360,
):
    match = find_latest_analysis(radar_time, max_age_minutes=max_age_minutes)
    if match is None:
        return None
    return match, download_analysis(match, output_dir)
