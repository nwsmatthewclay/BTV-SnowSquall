"""Conservative historical MRMS acquisition via the IEM raster-to-netCDF service.

IEM documents archived MRMS GIS rasters for selected products back to October
2014. This adapter never selects a product time after the requested radar scan.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

IEM_START = datetime(2014, 10, 1, tzinfo=timezone.utc)
PRODUCTS = {
    "mrms_lcref": {
        "description": "MRMS lowest-elevation composite reflectivity",
        "unit": "dBZ",
        "interval_minutes": 2,
    },
    "mrms_a2m": {
        "description": "MRMS two-minute precipitation accumulation",
        "unit": "mm",
        "interval_minutes": 2,
    },
    "mrms_p1h": {
        "description": "MRMS one-hour accumulated precipitation",
        "unit": "mm",
        "interval_minutes": 60,
    },
}


@dataclass(frozen=True)
class MrmsMatch:
    product: str
    valid_time: datetime
    url: str
    local_path: Path
    age_minutes: float


def available_for_time(radar_time: datetime) -> bool:
    return radar_time.astimezone(timezone.utc) >= IEM_START


def floor_product_time(radar_time: datetime, interval_minutes: int) -> datetime:
    radar_time = radar_time.astimezone(timezone.utc).replace(second=0, microsecond=0)
    minute = (radar_time.minute // interval_minutes) * interval_minutes
    return radar_time.replace(minute=minute)


def raster_netcdf_url(valid_time: datetime, product: str) -> str:
    if product not in PRODUCTS:
        raise ValueError(f"Unsupported MRMS product: {product}")
    valid_time = valid_time.astimezone(timezone.utc)
    stamp = valid_time.strftime("%Y%m%d%H%M")
    return (
        "https://mesonet.agron.iastate.edu/cgi-bin/request/"
        f"raster2netcdf.py?dstr={stamp}&prod={product}"
    )


def _exists(url: str) -> bool:
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(8, 20),
            headers={"Range": "bytes=0-0"},
        ) as response:
            return response.status_code in (200, 206)
    except requests.RequestException:
        return False


def find_latest(
    radar_time: datetime,
    product: str,
    max_age_minutes: int = 120,
) -> MrmsMatch | None:
    """Return the newest archived MRMS raster at or before radar_time."""
    if product not in PRODUCTS:
        raise ValueError(f"Unsupported MRMS product: {product}")

    radar_time = radar_time.astimezone(timezone.utc)
    if radar_time < IEM_START:
        return None

    interval = int(PRODUCTS[product]["interval_minutes"])
    candidate = floor_product_time(radar_time, interval)

    for offset in range(0, max_age_minutes + interval, interval):
        valid = candidate - timedelta(minutes=offset)
        if valid < IEM_START:
            break
        age = (radar_time - valid).total_seconds() / 60.0
        if age > max_age_minutes:
            continue
        url = raster_netcdf_url(valid, product)
        if _exists(url):
            filename = f"{product}_{valid:%Y%m%d%H%M}.nc"
            return MrmsMatch(
                product=product,
                valid_time=valid,
                url=url,
                local_path=Path(filename),
                age_minutes=age,
            )
    return None


def download(match: MrmsMatch, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / match.local_path.name
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    partial = destination.with_suffix(".part")
    try:
        with requests.get(
            match.url,
            stream=True,
            timeout=(15, 180),
        ) as response:
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
        raise IOError(f"Empty MRMS download: {match.url}")

    partial.replace(destination)
    return destination
