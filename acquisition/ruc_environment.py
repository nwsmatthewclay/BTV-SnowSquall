"""Acquire time-matched historical RUC 13-km analyses.

RUC was the hourly predecessor to RAP and covers the historical Banacos
period. The NCEI archive exposes GRIB2 analyses through THREDDS.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

BASE = "https://www.ncei.noaa.gov/thredds/fileServer"
DATASETS = ("model-ruc130anl-old", "model-ruc130anl")


@dataclass(frozen=True)
class RucMatch:
    valid_time: datetime
    url: str
    local_path: Path
    age_minutes: float


def ruc_analysis_url(valid_time: datetime) -> str:
    valid_time = valid_time.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    stamp = valid_time.strftime("%Y%m%d")
    month = valid_time.strftime("%Y%m")
    filename = f"ruc2anl_130_{stamp}_{valid_time:%H}00_000.grb2"
    # The old archive contains the early GRIB2 period used by this project.
    return f"{BASE}/model-ruc130anl-old/{month}/{stamp}/{filename}"


def _candidate_urls(valid_time: datetime):
    valid_time = valid_time.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    stamp = valid_time.strftime("%Y%m%d")
    month = valid_time.strftime("%Y%m")
    filename = f"ruc2anl_130_{stamp}_{valid_time:%H}00_000.grb2"
    for dataset in DATASETS:
        yield f"{BASE}/{dataset}/{month}/{stamp}/{filename}"


def find_latest_analysis(radar_time: datetime, max_age_minutes: int = 180):
    radar_time = radar_time.astimezone(timezone.utc).replace(second=0, microsecond=0)
    for offset in range(0, max_age_minutes + 60, 60):
        valid = (radar_time - timedelta(minutes=offset)).replace(minute=0)
        for url in _candidate_urls(valid):
            try:
                response = requests.head(url, timeout=20, allow_redirects=True)
                if response.status_code == 200:
                    age = (radar_time - valid).total_seconds() / 60.0
                    if age <= max_age_minutes:
                        return RucMatch(
                            valid,
                            url,
                            Path(url.rsplit("/", 1)[-1]),
                            age,
                        )
            except requests.RequestException:
                continue
    return None


def download_analysis(match: RucMatch, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / match.local_path.name
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    with requests.get(match.url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)

    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise IOError(f"Empty RUC download: {match.url}")

    partial.replace(destination)
    return destination


def acquire_for_radar_time(
    radar_time: datetime,
    output_dir: Path = Path("data/raw/RUC"),
    max_age_minutes: int = 180,
):
    match = find_latest_analysis(radar_time, max_age_minutes=max_age_minutes)
    if match is None:
        return None
    return match, download_analysis(match, output_dir)
