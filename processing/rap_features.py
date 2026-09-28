"""Extract leakage-safe RAP environmental features at an object centroid.

The first implementation focuses on variables directly present in the RAP
13-km hybrid analysis file. Derived profile metrics can be added without
changing the object record schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np


CANONICAL = (
    "cape_jkg",
    "cin_jkg",
    "pwat_mm",
    "surface_visibility_m",
    "surface_gust_ms",
    "surface_temperature_k",
)


def _open(path: Path, type_of_level: str, short_name: str):
    import xarray as xr

    return xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={
            "filter_by_keys": {
                "typeOfLevel": type_of_level,
                "shortName": short_name,
            },
            "indexpath": "",
        },
    )


def _nearest(ds, lat: float, lon: float, variable: str):
    if variable not in ds:
        return None

    lat_name = "latitude" if "latitude" in ds.coords else "lat"
    lon_name = "longitude" if "longitude" in ds.coords else "lon"

    lats = ds[lat_name].values
    lons = ds[lon_name].values

    # RAP Lambert grid is 2-D; use a simple squared degree distance for the
    # nearest grid point. The resulting point is close enough for object-scale
    # feature attachment, and avoids inventing interpolation at this stage.
    distance = (lats - lat) ** 2 + ((lons - lon) * np.cos(np.deg2rad(lat))) ** 2
    idx = np.unravel_index(np.nanargmin(distance), distance.shape)
    value = ds[variable].values[idx]
    return float(value) if np.isfinite(value) else None


def extract_features(
    path: Path,
    latitude: float,
    longitude: float,
    radar_time: datetime,
) -> dict:
    """Extract point features only from a RAP analysis at/before radar_time."""
    radar_time = radar_time.astimezone(timezone.utc)

    features = {name: None for name in CANONICAL}
    source_valid_time = None

    for short_name, key in (
        ("cape", "cape_jkg"),
        ("cin", "cin_jkg"),
        ("pwat", "pwat_mm"),
        ("vis", "surface_visibility_m"),
        ("gust", "surface_gust_ms"),
        ("tmp", "surface_temperature_k"),
    ):
        level = "surface" if key not in {"cape_jkg", "cin_jkg", "pwat_mm"} else "surface"
        try:
            with _open(path, level, short_name) as ds:
                features[key] = _nearest(ds, latitude, longitude, list(ds.data_vars)[0])
                if source_valid_time is None:
                    valid = ds.attrs.get("valid_time")
                    if valid is not None:
                        source_valid_time = datetime.fromtimestamp(
                            np.datetime64(valid, "s").astype(int), tz=timezone.utc
                        )
        except Exception:
            # Missing individual GRIB messages should not invalidate the whole
            # object record; the field remains explicitly unavailable.
            continue

    if source_valid_time is not None and source_valid_time > radar_time:
        raise ValueError("RAP feature source is newer than radar observation")

    if features["pwat_mm"] is not None:
        # RAP PWAT is kg/m^2, numerically equivalent to mm.
        features["pwat_mm"] = float(features["pwat_mm"])

    return {
        "source": "RAP",
        "source_valid_time_utc": source_valid_time.isoformat() if source_valid_time else None,
        "source_file": path.name,
        "age_minutes": (
            (radar_time - source_valid_time).total_seconds() / 60.0
            if source_valid_time is not None else None
        ),
        "fields": features,
    }
