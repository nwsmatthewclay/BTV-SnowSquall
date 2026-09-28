"""Read NEXRAD Level-II volumes with Py-ART and xradar fallback."""
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


def _tag_backend(radar, backend: str):
    metadata = getattr(radar, "metadata", None)
    if not isinstance(metadata, dict):
        try:
            radar.metadata = {}
            metadata = radar.metadata
        except Exception:
            return radar
    metadata["reader_backend"] = backend
    return radar


def read_level2(path):
    """Read one Level-II volume, falling back to xradar if Py-ART fails."""
    path = Path(path)
    try:
        import pyart
        radar = pyart.io.read_nexrad_archive(str(path))
        return _tag_backend(radar, "pyart_legacy_nexrad")
    except Exception as pyart_exc:
        try:
            import xradar as xd
            tree = xd.io.open_nexradlevel2_datatree(str(path))
            radar = tree.pyart.to_radar()
            return _tag_backend(radar, "xradar")
        except Exception as xradar_exc:
            raise RuntimeError(
                "Both Level-II readers failed. "
                f"Py-ART {type(pyart_exc).__name__}: {pyart_exc}; "
                f"xradar {type(xradar_exc).__name__}: {xradar_exc}"
            ) from xradar_exc


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
        "reader_backend": getattr(radar, "metadata", {}).get("reader_backend"),
        "scan_time_utc": first_time.isoformat() if first_time else None,
        "time_units": time_units,
        "nsweeps": int(radar.nsweeps),
        "nrays": int(radar.nrays),
        "ngates": int(radar.ngates),
        "fields": sorted(radar.fields),
    }
