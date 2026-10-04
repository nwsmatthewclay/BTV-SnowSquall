"""Geographic Cartesian gridding for historical NEXRAD object reconstruction.

The object detector should operate on a common Cartesian grid rather than native
radar row/column coordinates. This keeps object geometry and motion comparable
between scans and radar sites.
"""
from __future__ import annotations

import numpy as np
import pyart

from processing.radar_sites import radar_origin_for_site


def grid_lowest_sweep(
    radar,
    field_name: str | list[str],
    *,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    grid_size_km: float = 180.0,
    spacing_km: float = 1.0,
):
    """Grid the lowest radar sweep to a fixed horizontal Cartesian grid.

    Returns a Py-ART Grid with one vertical level. The grid origin is the radar
    itself unless an explicit geographic origin is supplied.
    """
    radar_sw = radar.extract_sweeps([0])
    n = int(round((2 * grid_size_km) / spacing_km)) + 1
    half_m = grid_size_km * 1000.0
    spacing_m = spacing_km * 1000.0

    fields = [field_name] if isinstance(field_name, str) else list(field_name)
    fields = list(dict.fromkeys(fields))
    kwargs = {
        "grid_shape": (1, n, n),
        "grid_limits": ((0.0, 0.0), (-half_m, half_m), (-half_m, half_m)),
        "fields": fields,
        "gridding_algo": "map_gates_to_grid",
        "roi_func": "dist_beam",
        "min_radius": max(750.0, spacing_m * 1.5),
    }
    if origin_lat is not None and origin_lon is not None:
        kwargs["grid_origin"] = (origin_lat, origin_lon)

    return pyart.map.grid_from_radars((radar_sw,), **kwargs)


def lowest_valid_sweep(radar, field_name: str) -> int | None:
    """Return the lowest-elevation sweep containing finite data for a field.

    NEXRAD Level-II volumes do not guarantee that sweep 0 contains valid data
    for every moment. In particular, base velocity can be absent/masked on the
    lowest reflectivity sweep. Selecting the first sweep with actual finite
    field data prevents a valid velocity field from being discarded simply
    because it lives on a separate lowest-elevation cut.
    """
    if field_name not in getattr(radar, "fields", {}):
        return None
    field = radar.fields[field_name].get("data")
    if field is None:
        return None
    starts = np.asarray(radar.sweep_start_ray_index["data"], dtype=int)
    ends = np.asarray(radar.sweep_end_ray_index["data"], dtype=int)
    for sweep, (start, end) in enumerate(zip(starts, ends)):
        data = field[int(start):int(end) + 1]
        if np.ma.isMaskedArray(data):
            finite = np.isfinite(np.ma.filled(data, np.nan))
        else:
            finite = np.isfinite(np.asarray(data, dtype=float))
        if bool(np.any(finite)):
            return int(sweep)
    return None


def grid_lowest_available_sweep(
    radar,
    field_name: str,
    *,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    grid_size_km: float = 180.0,
    spacing_km: float = 1.0,
):
    """Grid the lowest sweep that actually contains data for field_name.

    This is intentionally separate from grid_lowest_sweep, whose historical
    behavior remains useful when a caller needs all fields from literal sweep 0.
    All returned grids use identical geography/resolution so independently
    gridded moments can be combined on one Cartesian grid.
    """
    sweep = lowest_valid_sweep(radar, field_name)
    if sweep is None:
        return None

    radar_sw = radar.extract_sweeps([sweep])
    n = int(round((2 * grid_size_km) / spacing_km)) + 1
    half_m = grid_size_km * 1000.0
    spacing_m = spacing_km * 1000.0
    kwargs = {
        "grid_shape": (1, n, n),
        "grid_limits": ((0.0, 0.0), (-half_m, half_m), (-half_m, half_m)),
        "fields": [field_name],
        "gridding_algo": "map_gates_to_grid",
        "roi_func": "dist_beam",
        "min_radius": max(750.0, spacing_m * 1.5),
    }
    if origin_lat is not None and origin_lon is not None:
        kwargs["grid_origin"] = (origin_lat, origin_lon)
    return pyart.map.grid_from_radars((radar_sw,), **kwargs)

def grid_field_2d(grid, field_name: str) -> np.ndarray:
    """Return the lowest grid level as a float array with masked values NaN."""
    data = grid.fields[field_name]["data"][0]
    if np.ma.isMaskedArray(data):
        return data.filled(np.nan).astype(float)
    return np.asarray(data, dtype=float)


def grid_latlon(grid):
    """Return 2-D latitude/longitude arrays for the lowest grid level."""
    lon, lat = grid.get_point_longitude_latitude()
    return np.asarray(lat), np.asarray(lon)


def grid_site_origin(radar_site: str | None):
    """Return the canonical latitude/longitude origin used for a radar site."""
    return radar_origin_for_site(radar_site)
