"""Canonical radar-site metadata used for geographic reconstruction."""
from __future__ import annotations

import numpy as np

# Pilot / BTV-domain radar coordinates. These match the NWS/ROC site data.
RADAR_ORIGINS = {
    "KCXX": (44.511, -73.166),
    "KTYX": (43.756, -75.680),
    "KBTV": (44.472, -73.154),
}


def radar_origin_for_site(radar_site: str | None):
    """Return a canonical (latitude, longitude) origin for a known radar."""
    if not radar_site:
        return None
    return RADAR_ORIGINS.get(str(radar_site).upper().strip())


def apply_radar_origin(radar, radar_origin):
    """Apply a trusted radar origin and reset dependent gate geolocation.

    Historical Level-II volumes can carry incomplete or corrupted site
    coordinates. Py-ART's geographic gate coordinates are derived from the
    radar latitude/longitude, so those attributes must be repaired before
    geographic gridding or native gate sampling.
    """
    if radar_origin is None:
        return radar

    lat, lon = map(float, radar_origin)
    radar.latitude["data"] = np.array([lat], dtype=float)
    radar.longitude["data"] = np.array([lon], dtype=float)

    reset = getattr(radar, "init_gate_longitude_latitude", None)
    if callable(reset):
        reset()

    return radar
