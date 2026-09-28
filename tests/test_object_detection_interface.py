import numpy as np

from processing.object_detection import DetectionConfig, detect_objects


def test_detection_interface_delegates_to_canonical_detector():
    field = np.full((10, 10), np.nan)
    field[2:7, 2:7] = 30.0
    objects = detect_objects(
        field,
        DetectionConfig(
            reflectivity_threshold_dbz=20.0,
            core_threshold_dbz=25.0,
            min_area_km2=4.0,
            spacing_km=1.0,
        ),
    )
    assert len(objects) == 1
    assert objects[0]["pixel_count"] == 25
    assert objects[0]["max_reflectivity_dbz"] == 30.0
    assert objects[0]["core_pixel_count"] == 25


def test_min_area_converts_to_pixels():
    assert DetectionConfig(min_area_km2=4.0, spacing_km=1.0).min_pixels == 4
    assert DetectionConfig(min_area_km2=4.0, spacing_km=2.0).min_pixels == 1
