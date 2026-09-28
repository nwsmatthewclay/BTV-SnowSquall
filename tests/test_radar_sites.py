from processing.radar_grid import grid_site_origin
from processing.radar_sites import radar_origin_for_site


def test_known_radar_origins():
    assert radar_origin_for_site("KCXX") == (44.511, -73.166)
    assert radar_origin_for_site("KTYX") == (43.755, -75.676)
    assert radar_origin_for_site("KBTV") == (44.472, -73.154)


def test_radar_origin_lookup_is_normalized_and_unknown_safe():
    assert grid_site_origin(" kcxx ") == (44.511, -73.166)
    assert radar_origin_for_site("UNKNOWN") is None
