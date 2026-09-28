import numpy as np

from processing.radar_grid import grid_site_origin
from processing.radar_sites import radar_origin_for_site


def test_known_radar_origins():
    assert radar_origin_for_site("KCXX") == (44.511, -73.166)
    assert radar_origin_for_site("KTYX") == (43.756, -75.680)
    assert radar_origin_for_site("KBTV") == (44.472, -73.154)


def test_radar_origin_lookup_is_normalized_and_unknown_safe():
    assert grid_site_origin(" kcxx ") == (44.511, -73.166)
    assert radar_origin_for_site("UNKNOWN") is None


def test_apply_radar_origin_repairs_site_and_resets_gate_coordinates():
    class DummyRadar:
        def __init__(self):
            self.latitude = {"data": np.array([0.0])}
            self.longitude = {"data": np.array([0.0])}
            self.reset_called = False

        def init_gate_longitude_latitude(self):
            self.reset_called = True

    from processing.radar_sites import apply_radar_origin

    radar = DummyRadar()
    result = apply_radar_origin(radar, (44.511, -73.166))

    assert result is radar
    assert float(radar.latitude["data"][0]) == 44.511
    assert float(radar.longitude["data"][0]) == -73.166
    assert radar.reset_called
