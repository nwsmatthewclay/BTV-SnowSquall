"""Read NEXRAD Level-II volumes with Py-ART.

This module does not download data; it converts one archived Level-II volume
into a radar object with explicit field-name discovery and provenance.
"""
from __future__ import annotations
from pathlib import Path

FIELD_ALIASES = {
    "reflectivity": ("reflectivity", "DBZH", "dBZ"),
    "velocity": ("velocity", "VEL"),
    "spectrum_width": ("spectrum_width", "WIDTH"),
    "zdr": ("differential_reflectivity", "ZDR"),
    "rhohv": ("cross_correlation_ratio", "RHOHV"),
    "kdp": ("specific_differential_phase", "KDP"),
}


def read_level2(path):
    try:
        import pyart
    except ImportError as exc:
        raise ImportError("Install requirements-science.txt to read Level-II data") from exc
    return pyart.io.read_nexrad_archive(str(Path(path)))


def resolve_fields(radar):
    available = set(radar.fields)
    resolved = {}
    for canonical, aliases in FIELD_ALIASES.items():
        resolved[canonical] = next((name for name in aliases if name in available), None)
    return resolved


def volume_metadata(radar, source_path=None):
    time_units = radar.time.get("units") if hasattr(radar, "time") else None
    first_time = None
    try:
        import pyart
        first_time = pyart.util.datetime_from_radar(radar)
    except Exception:
        pass

    return {
        "source_path": str(source_path) if source_path else None,
        "radar_id": getattr(radar, "metadata", {}).get("instrument_name"),
        "scan_time_utc": first_time.isoformat() if first_time else None,
        "time_units": time_units,
        "nsweeps": int(radar.nsweeps),
        "nrays": int(radar.nrays),
        "ngates": int(radar.ngates),
        "fields": sorted(radar.fields),
    }
