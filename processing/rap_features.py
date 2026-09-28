"""Extract time-matched RAP environmental features at a radar-object centroid.

All values come from the RAP analysis valid at or before the radar scan time.
The extractor intentionally records missing fields as null rather than
silently substituting a different model cycle or a future analysis.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr


FIELD_SPECS = {
    "visibility_m": ("surface", "vis", None),
    "gust_ms": ("surface", "gust", None),
    "surface_temperature_k": ("surface", "tmp", None),
    "cape_jkg": ("surface", "cape", None),
    "cin_jkg": ("surface", "cin", None),
    "pwat_mm": ("entireAtmosphere", "pwat", None),
    "mlcape_jkg": ("heightAboveGroundLayer", "cape", (180, 0)),
    "mlcin_jkg": ("heightAboveGroundLayer", "cin", (180, 0)),
    "mucape_jkg": ("heightAboveGroundLayer", "cape", (255, 0)),
    "mucin_jkg": ("heightAboveGroundLayer", "cin", (255, 0)),
    "srh01_m2s2": ("heightAboveGroundLayer", "hlcy", (1000, 0)),
    "srh03_m2s2": ("heightAboveGroundLayer", "hlcy", (3000, 0)),
    "shear_u_0_6km_ms": ("heightAboveGroundLayer", "vucsh", (6000, 0)),
    "shear_v_0_6km_ms": ("heightAboveGroundLayer", "vvcsh", (6000, 0)),
    "u10_ms": ("heightAboveGround", "u", 10),
    "v10_ms": ("heightAboveGround", "v", 10),
    "temperature_2m_k": ("heightAboveGround", "tmp", 2),
    "dewpoint_2m_k": ("heightAboveGround", "dpt", 2),
    "rh_2m_pct": ("heightAboveGround", "r", 2),
}


def _valid_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt64 = np.datetime64(value, "s")
            dt = datetime.fromtimestamp(int(dt64.astype("int64")), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
    return dt.astimezone(timezone.utc)


def _open_field(path: Path, type_of_level: str, short_name: str, level=None):
    filters = {"typeOfLevel": type_of_level, "shortName": short_name}
    if level is not None:
        if type_of_level == "heightAboveGround":
            filters["level"] = level
        elif type_of_level == "heightAboveGroundLayer":
            top, bottom = level
            filters["topLevel"] = top
            filters["bottomLevel"] = bottom

    return xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"filter_by_keys": filters, "indexpath": ""},
    )


def _nearest(ds, latitude: float, longitude: float):
    if not ds.data_vars:
        return None

    lat_name = next((x for x in ("latitude", "lat") if x in ds.coords), None)
    lon_name = next((x for x in ("longitude", "lon") if x in ds.coords), None)
    if lat_name is None or lon_name is None:
        return None

    lats = np.asarray(ds[lat_name].values)
    lons = np.asarray(ds[lon_name].values)
    distance = (lats - latitude) ** 2 + (
        (lons - longitude) * np.cos(np.deg2rad(latitude))
    ) ** 2
    idx = np.unravel_index(np.nanargmin(distance), distance.shape)

    variable = next(iter(ds.data_vars))
    value = np.asarray(ds[variable].values)[idx]
    return float(value) if np.isfinite(value) else None


def extract_features(
    path: Path,
    latitude: float,
    longitude: float,
    radar_time: datetime,
) -> dict:
    radar_time = radar_time.astimezone(timezone.utc)
    values = {name: None for name in FIELD_SPECS}
    source_valid_time = None
    failures = {}

    for name, (level_type, short_name, level) in FIELD_SPECS.items():
        try:
            with _open_field(path, level_type, short_name, level) as ds:
                valid = _valid_time(ds.attrs.get("valid_time"))
                if valid is not None:
                    if valid > radar_time:
                        raise ValueError(
                            f"future RAP analysis {valid.isoformat()} > "
                            f"radar {radar_time.isoformat()}"
                        )
                    source_valid_time = source_valid_time or valid
                values[name] = _nearest(ds, latitude, longitude)
        except Exception as exc:
            failures[name] = type(exc).__name__

    if values["pwat_mm"] is not None:
        # RAP PWAT is kg m^-2, numerically equivalent to mm of liquid water.
        values["pwat_mm"] = float(values["pwat_mm"])

    shear_u = values.get("shear_u_0_6km_ms")
    shear_v = values.get("shear_v_0_6km_ms")
    values["shear_0_6km_ms"] = (
        float(np.hypot(shear_u, shear_v))
        if shear_u is not None and shear_v is not None else None
    )

    return {
        "source": "RAP",
        "source_valid_time_utc": (
            source_valid_time.isoformat() if source_valid_time else None
        ),
        "age_minutes": (
            (radar_time - source_valid_time).total_seconds() / 60.0
            if source_valid_time else None
        ),
        "fields": values,
        "missing_fields": sorted(failures),
        "status": "complete" if not failures else "partial",
    }
