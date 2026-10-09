"""Regression tests for conservative live radar clutter filtering."""
import numpy as np

from scripts.build_live_radar_mosaic import _clean_field


def test_low_rhohv_weak_and_moderate_echoes_are_suppressed():
    reflectivity = np.full((7, 7), 20.0)
    rhohv = np.full((7, 7), 0.95)
    rhohv[3, 3] = 0.64

    cleaned = _clean_field(reflectivity, rhohv)

    assert np.isnan(cleaned[3, 3])
    assert cleaned[3, 2] == 20.0


def test_low_rhohv_filter_does_not_blank_echoes_at_or_above_30_dbz():
    reflectivity = np.full((7, 7), 31.0)
    rhohv = np.full((7, 7), 0.95)
    rhohv[3, 3] = 0.40

    cleaned = _clean_field(reflectivity, rhohv)

    assert cleaned[3, 3] == 31.0


def test_clean_field_preserves_supported_weak_snow_echoes():
    reflectivity = np.full((7, 7), 8.0)
    rhohv = np.full((7, 7), 0.95)

    cleaned = _clean_field(reflectivity, rhohv)

    assert np.isfinite(cleaned[3, 3])
    assert cleaned[3, 3] == 8.0


def test_clean_field_does_not_change_raw_input_array():
    reflectivity = np.full((7, 7), 20.0)
    rhohv = np.full((7, 7), 0.95)
    rhohv[3, 3] = 0.40
    original = reflectivity.copy()

    _clean_field(reflectivity, rhohv)

    np.testing.assert_array_equal(reflectivity, original)
