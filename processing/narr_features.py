"""Extract a common historical environment subset from NARR-A GRIB1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr


FIELD_SPECS = {
    "visibility_m": ("surface", "vis", None),
    "surface_temperature_k": ("surface", "t", None),
    "cape_jkg": ("surface", "cape", None),
    "pwat_mm": ("entireAtmosphere", "pwat", None),
    "temperature_2m_k": ("heightAboveGround", "t", 2),
    "rh_2m_pct": ("heightAboveGround", "r", 2),
    "u10_ms": ("heightAboveGround", "u", 10),
    "v10_ms": ("heightAboveGround", "v", 10),
}

# NARR analyses are large GRIB files and many radar objects share the same
# 3-hourly analysis. Keep the decoded field datasets alive and reuse them.
# This changes performance only; it does not change the selected analysis.
_DATASET_CACHE: dict[tuple[str, str, str, int | None], xr.Dataset] = {}


def _open_field(path: Path, type_of_level: str, short_name: str, level=None):
    key = (str(path.resolve()), type_of_level, short_name, level)
    cached = _DATASET_CACHE.get(key)
    if cached is not None:
        return cached

    filters = {"typeOfLevel": type_of_level, "shortName": short_name}
    if level is not None:
        filters["level"] = level

    ds = xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"filter_by_keys": filters, "indexpath": ""},
    )
    _DATASET_CACHE[key] = ds
    return ds


def clear_dataset_cache():
    """Release cached NARR datasets; primarily useful for tests/workers."""
    for ds in _DATASET_CACHE.values():
        try:
            ds.close()
        except Exception:
            pass
    _DATASET_CACHE.clear()


def _nearest(ds, latitude, longitude):
    if not ds.data_vars:
        return None

    if "latitude" in ds.coords and "longitude" in ds.coords:
        lat = np.asarray(ds["latitude"].values, dtype=float)
        lon = np.asarray(ds["longitude"].values, dtype=float)
        distance = (lat - latitude) ** 2 + (
            (lon - longitude) * np.cos(np.deg2rad(latitude))
        ) ** 2
        idx = np.unravel_index(np.nanargmin(distance), distance.shape)
    elif "x" in ds.coords and "y" in ds.coords:
        raise ValueError("NARR dataset lacks latitude/longitude coordinates")
    else:
        raise ValueError("NARR dataset lacks geographic coordinates")

    variable = next(iter(ds.data_vars))
    value = np.asarray(ds[variable].values)
    if value.ndim > 2:
        value = value.reshape((-1,) + value.shape[-2:])[0]
    value = value[idx]
    return float(value) if np.isfinite(value) else None


def extract_features(
    path: Path,
    latitude: float,
    longitude: float,
    radar_time: datetime,
    expected_valid_time=None,
):
    radar_time = radar_time.astimezone(timezone.utc)
    expected_valid_time = (
        expected_valid_time.astimezone(timezone.utc)
        if expected_valid_time else None
    )
    values = {name: None for name in FIELD_SPECS}
    failures = {}

    for name, (level_type, short_name, level) in FIELD_SPECS.items():
        try:
            ds = _open_field(path, level_type, short_name, level)
            values[name] = _nearest(ds, latitude, longitude)
        except Exception as exc:
            failures[name] = type(exc).__name__

    temp = values.get("temperature_2m_k")
    rh = values.get("rh_2m_pct")
    if temp is not None and rh is not None and rh > 0:
        tc = temp - 273.15
        gamma = np.log(rh / 100.0) + (17.625 * tc) / (243.04 + tc)
        td_c = 243.04 * gamma / (17.625 - gamma)
        values["dewpoint_2m_k"] = float(td_c + 273.15)
    else:
        values["dewpoint_2m_k"] = None

    u10 = values.get("u10_ms")
    v10 = values.get("v10_ms")
    values["wind_10m_ms"] = (
        float(np.hypot(u10, v10)) if u10 is not None and v10 is not None else None
    )
    values["wind_10m_kt"] = (
        values["wind_10m_ms"] * 1.943844
        if values["wind_10m_ms"] is not None else None
    )

    return {
        "source": "NARR",
        "source_valid_time_utc": (
            expected_valid_time.isoformat() if expected_valid_time else None
        ),
        "age_minutes": (
            (radar_time - expected_valid_time).total_seconds() / 60.0
            if expected_valid_time else None
        ),
        "fields": values,
        "missing_fields": sorted(failures),
        "status": "complete" if not failures else "partial",
    }
