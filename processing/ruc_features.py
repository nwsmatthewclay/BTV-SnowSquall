"""Extract common environmental fields from historical RUC 13-km GRIB2.

RUC and RAP are different model generations, so this module deliberately
returns a documented common subset rather than pretending the fields are
identical. Missing diagnostics remain null.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr
from pyproj import CRS, Transformer

FIELD_SPECS = {
    "visibility_m": ("surface", "vis", None),
    "gust_ms": ("surface", "gust", None),
    "surface_temperature_k": ("surface", "tmp", None),
    "cape_jkg": ("surface", "cape", None),
    "pwat_mm": ("entireAtmosphere", "pwat", None),
    "temperature_2m_k": ("heightAboveGround", "tmp", 2),
    "dewpoint_2m_k": ("heightAboveGround", "dpt", 2),
    "rh_2m_pct": ("heightAboveGround", "r", 2),
    "u10_ms": ("heightAboveGround", "u", 10),
    "v10_ms": ("heightAboveGround", "v", 10),
}

RUC_CRS = CRS.from_proj4(
    "+proj=lcc +lat_1=25 +lat_2=25 +lat_0=25 "
    "+lon_0=-95 +a=6371229 +b=6371229 +units=m +no_defs"
)
LL_CRS = CRS.from_epsg(4326)


def _open_field(path: Path, type_of_level: str, short_name: str, level=None):
    filters = {"typeOfLevel": type_of_level, "shortName": short_name}
    if level is not None:
        filters["level"] = level
    return xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"filter_by_keys": filters, "indexpath": ""},
    )


def _nearest(ds, latitude, longitude):
    if not ds.data_vars or "x" not in ds.coords or "y" not in ds.coords:
        return None

    x = np.asarray(ds["x"].values, dtype=float)
    y = np.asarray(ds["y"].values, dtype=float)
    xx, yy = np.meshgrid(x, y)
    transformer = Transformer.from_crs(RUC_CRS, LL_CRS, always_xy=True)
    lon, lat = transformer.transform(xx * 1000.0, yy * 1000.0)
    distance = (lat - latitude) ** 2 + (
        (lon - longitude) * np.cos(np.deg2rad(latitude))
    ) ** 2
    idx = np.unravel_index(np.nanargmin(distance), distance.shape)

    variable = next(iter(ds.data_vars))
    value = np.asarray(ds[variable].values)
    if value.ndim > 2:
        value = value.reshape((-1,) + value.shape[-2:])[0]
    value = value[idx]
    return float(value) if np.isfinite(value) else None


def extract_features(path: Path, latitude: float, longitude: float, radar_time: datetime, expected_valid_time=None):
    radar_time = radar_time.astimezone(timezone.utc)
    expected_valid_time = expected_valid_time.astimezone(timezone.utc) if expected_valid_time else None
    values = {name: None for name in FIELD_SPECS}
    failures = {}

    for name, (level_type, short_name, level) in FIELD_SPECS.items():
        try:
            with _open_field(path, level_type, short_name, level) as ds:
                values[name] = _nearest(ds, latitude, longitude)
        except Exception as exc:
            failures[name] = type(exc).__name__

    gust = values.get("gust_ms")
    values["gust_kt"] = float(gust) * 1.943844 if gust is not None else None
    u10 = values.get("u10_ms")
    v10 = values.get("v10_ms")
    values["wind_10m_ms"] = float(np.hypot(u10, v10)) if u10 is not None and v10 is not None else None
    values["wind_10m_kt"] = (
        values["wind_10m_ms"] * 1.943844
        if values["wind_10m_ms"] is not None else None
    )

    return {
        "source": "RUC",
        "source_valid_time_utc": expected_valid_time.isoformat() if expected_valid_time else None,
        "age_minutes": (
            (radar_time - expected_valid_time).total_seconds() / 60.0
            if expected_valid_time else None
        ),
        "fields": values,
        "missing_fields": sorted(failures),
        "status": "complete" if not failures else "partial",
    }
