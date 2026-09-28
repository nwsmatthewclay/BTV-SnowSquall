"""Native multi-elevation vertical-structure sampling for radar objects."""
from __future__ import annotations

from math import atan2, cos, degrees, hypot, radians

import numpy as np


def _object_range_bearing(radar_lat, radar_lon, object_lat, object_lon):
    """Return approximate radar-relative range (km) and azimuth (degrees)."""
    mean_lat = radians((radar_lat + object_lat) / 2.0)
    dx_km = (object_lon - radar_lon) * 111.32 * cos(mean_lat)
    dy_km = (object_lat - radar_lat) * 110.57
    range_km = hypot(dx_km, dy_km)
    azimuth = (degrees(atan2(dx_km, dy_km)) + 360.0) % 360.0
    return range_km, azimuth


def _circular_difference(a, b):
    return np.abs((np.asarray(a) - b + 180.0) % 360.0 - 180.0)


def summarize_vertical_profile(reflectivity_dbz, altitude_m, threshold_dbz=20.0):
    """Summarize valid echo above a reflectivity threshold."""
    values = np.asarray(reflectivity_dbz, dtype=float).ravel()
    heights = np.asarray(altitude_m, dtype=float).ravel()
    valid = np.isfinite(values) & np.isfinite(heights) & (values >= threshold_dbz)

    if not np.any(valid):
        return {
            "echo_top_km": np.nan,
            "top_minus_base_km": np.nan,
            "vertical_reflectivity_gradient": np.nan,
            "vertical_valid_points": 0,
        }

    values = values[valid]
    heights = heights[valid]
    order = np.argsort(heights)
    values = values[order]
    heights = heights[order]

    top_km = float(np.max(heights) / 1000.0)
    depth_km = float((np.max(heights) - np.min(heights)) / 1000.0)

    gradient = np.nan
    unique_heights = np.unique(heights)
    if len(unique_heights) >= 2:
        try:
            gradient = float(np.polyfit(heights / 1000.0, values, 1)[0])
        except (TypeError, ValueError, np.linalg.LinAlgError):
            gradient = np.nan

    return {
        "echo_top_km": top_km,
        "top_minus_base_km": depth_km,
        "vertical_reflectivity_gradient": gradient,
        "vertical_valid_points": int(len(values)),
    }


def summarize_vertical_structure(
    radar,
    object_lat: float,
    object_lon: float,
    reflectivity_field: str,
    threshold_dbz: float = 20.0,
    ray_half_width: int = 1,
    gate_half_width: int = 2,
    max_sweeps: int | None = None,
):
    """Sample a small native-radar neighborhood through the elevation stack.

    The sampler follows the object's radar-relative bearing and range, takes a
    few neighboring rays/gates on each sweep, and uses native gate altitude.
    It is intentionally a vertical-profile diagnostic, not a replacement for
    full 3-D volume gridding.
    """
    if not hasattr(radar, "fields") or reflectivity_field not in radar.fields:
        return {
            "echo_top_km": np.nan,
            "top_minus_base_km": np.nan,
            "vertical_reflectivity_gradient": np.nan,
            "vertical_valid_points": 0,
        }

    radar_lat = float(np.asarray(radar.latitude["data"]).reshape(-1)[0])
    radar_lon = float(np.asarray(radar.longitude["data"]).reshape(-1)[0])
    range_km, bearing_deg = _object_range_bearing(
        radar_lat, radar_lon, float(object_lat), float(object_lon)
    )

    if not np.isfinite(range_km):
        return {
            "echo_top_km": np.nan,
            "top_minus_base_km": np.nan,
            "vertical_reflectivity_gradient": np.nan,
            "vertical_valid_points": 0,
        }

    # Native Level-II gate ranges are shared across sweeps for a volume.
    ranges_m = np.asarray(radar.range["data"], dtype=float)
    center_gate = int(np.abs(ranges_m - range_km * 1000.0).argmin())
    gate_lo = max(0, center_gate - gate_half_width)
    gate_hi = min(len(ranges_m), center_gate + gate_half_width + 1)
    gate_indices = np.arange(gate_lo, gate_hi)

    sample_values = []
    sample_heights = []

    sweep_count = int(getattr(radar, "nsweeps", 0))
    if max_sweeps is not None:
        sweep_count = min(sweep_count, int(max_sweeps))

    # Py-ART documents get_gate_x_y_z as the sweep-specific Cartesian gate
    # geometry; use its z coordinate for altitude after selecting the native
    # neighboring ray/gates.
    import pyart

    radar_alt_m = float(np.asarray(radar.altitude["data"]).reshape(-1)[0])

    for sweep in range(sweep_count):
        try:
            azimuths = np.asarray(radar.get_azimuth(sweep), dtype=float)
            elevations = np.asarray(radar.get_elevation(sweep), dtype=float)
            field = np.ma.asarray(
                radar.get_field(sweep, reflectivity_field, copy=False)
            ).filled(np.nan).astype(float)

            if field.ndim != 2 or not len(azimuths):
                continue

            ray_order = np.argsort(_circular_difference(azimuths, bearing_deg))
            ray_indices = ray_order[: max(1, 2 * ray_half_width + 1)]
            ray_indices = np.asarray(ray_indices, dtype=int)

            selected_values = field[np.ix_(ray_indices, gate_indices)]
            selected_az = azimuths[ray_indices]
            selected_el = elevations[ray_indices]
            selected_ranges = ranges_m[gate_indices]

            # antenna_vectors_to_cartesian returns native x/y/z gate locations;
            # the z coordinate is relative to the radar altitude.
            _, _, z_m = pyart.core.antenna_vectors_to_cartesian(
                selected_ranges,
                selected_az,
                selected_el,
            )
            heights = radar_alt_m + np.asarray(z_m, dtype=float)

            sample_values.extend(selected_values.ravel().tolist())
            sample_heights.extend(heights.ravel().tolist())
        except Exception:
            # A malformed sweep should reduce vertical coverage, not discard
            # the complete object observation.
            continue

    return summarize_vertical_profile(
        sample_values,
        sample_heights,
        threshold_dbz=threshold_dbz,
    )
