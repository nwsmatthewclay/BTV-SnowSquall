import numpy as np

from scripts.process_live_volume import grid_point_to_geo


def test_grid_point_to_geo_bilinearly_interpolates_fractional_centroid():
    lat = np.array([[10.0, 10.0], [12.0, 12.0]])
    lon = np.array([[20.0, 22.0], [20.0, 22.0]])

    point = grid_point_to_geo(0.5, 0.5, lat, lon)

    assert point == (11.0, 21.0)


def test_grid_point_to_geo_preserves_subpixel_motion():
    lat = np.array([[44.0, 44.0], [45.0, 45.0]])
    lon = np.array([[-74.0, -73.0], [-74.0, -73.0]])

    first = grid_point_to_geo(0.40, 0.40, lat, lon)
    second = grid_point_to_geo(0.60, 0.60, lat, lon)

    assert first[0] < second[0]
    assert first[1] < second[1]
    assert first != second


def test_grid_point_to_geo_rejects_invalid_coordinates():
    lat = np.array([[44.0, 44.0], [45.0, 45.0]])
    lon = np.array([[-74.0, -73.0], [-74.0, -73.0]])

    assert grid_point_to_geo(float("nan"), 0.5, lat, lon) == (None, None)
