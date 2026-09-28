"""Canonical radar-site metadata used for geographic reconstruction."""
from __future__ import annotations

# Pilot / BTV-domain radar coordinates. These are also used by the viewer.
RADAR_ORIGINS = {
    "KCXX": (44.511, -73.166),
    "KTYX": (43.755, -75.676),
    "KBTV": (44.472, -73.154),
}


def radar_origin_for_site(radar_site: str | None):
    """Return a canonical (latitude, longitude) origin for a known radar."""
    if not radar_site:
        return None
    return RADAR_ORIGINS.get(str(radar_site).upper().strip())
