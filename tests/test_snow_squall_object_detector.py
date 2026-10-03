import numpy as np

from processing.object_detector import ObjectDetectionConfig, detect_reflectivity_objects


def test_uniform_snow_shield_is_not_an_object_without_enhancement():
    field = np.full((50, 50), 24.0)
    objects = detect_reflectivity_objects(
        field,
        ObjectDetectionConfig(
            threshold_dbz=20.0,
            core_threshold_dbz=30.0,
            min_pixels=4,
            max_pixels=3000,
            close_iterations=0,
            open_iterations=0,
            fill_holes=False,
        ),
    )
    assert objects == []


def test_sharp_20dbz_plus_band_is_detected():
    field = np.full((60, 60), 10.0)
    field[28:33, 8:52] = 24.0
    field[29:32, 12:48] = 30.0
    objects = detect_reflectivity_objects(
        field,
        ObjectDetectionConfig(
            threshold_dbz=20.0,
            core_threshold_dbz=30.0,
            min_pixels=4,
            max_pixels=3000,
            close_iterations=0,
            open_iterations=0,
            fill_holes=False,
        ),
    )
    assert len(objects) == 1
    obj = objects[0]
    assert obj["max_reflectivity_dbz"] >= 30.0
    assert obj["reflectivity_gradient_p90_dbkm"] >= 5.0
    assert obj["reflectivity_contrast_db"] >= 3.0


def test_small_noise_below_min_area_is_rejected():
    field = np.full((40, 40), 10.0)
    field[10:12, 10:12] = 25.0
    objects = detect_reflectivity_objects(
        field,
        ObjectDetectionConfig(
            threshold_dbz=20.0,
            core_threshold_dbz=30.0,
            min_pixels=6,
            close_iterations=0,
            open_iterations=0,
            fill_holes=False,
        ),
    )
    assert objects == []


def test_separated_cores_split_inside_one_broad_band():
    field = np.full((60, 80), 10.0)
    field[27:34, 5:75] = 23.0
    field[29:32, 15:20] = 34.0
    field[29:32, 60:65] = 36.0
    objects = detect_reflectivity_objects(
        field,
        ObjectDetectionConfig(
            threshold_dbz=20.0,
            core_threshold_dbz=30.0,
            min_pixels=4,
            max_pixels=3000,
            close_iterations=0,
            open_iterations=0,
            fill_holes=False,
            min_peak_separation_px=8,
        ),
    )
    assert len(objects) == 2


def test_elongated_band_with_multiple_cores_stays_one_object():
    field = np.full((80, 120), 10.0)
    field[36:43, 10:110] = 23.0
    field[38:41, 18:28] = 35.0
    field[38:41, 82:92] = 36.0
    objects = detect_reflectivity_objects(
        field,
        ObjectDetectionConfig(
            threshold_dbz=20.0,
            core_threshold_dbz=30.0,
            min_pixels=4,
            max_pixels=3000,
            close_iterations=0,
            open_iterations=0,
            fill_holes=False,
            min_peak_separation_px=8,
        ),
    )
    assert len(objects) == 1
    assert objects[0]["object_mode"] == "band"
    assert objects[0]["bbox_aspect_ratio"] >= 3.0


def test_coherent_base_velocity_can_rescue_modest_reflectivity():
    reflectivity = np.full((50, 50), 5.0)
    reflectivity[22:28, 15:35] = 18.0
    velocity_ms = np.zeros((50, 50), dtype=float)
    velocity_ms[22:28, 15:35] = 12.0

    objects = detect_reflectivity_objects(
        reflectivity,
        ObjectDetectionConfig(
            threshold_dbz=20.0,
            core_threshold_dbz=30.0,
            min_pixels=4,
            max_pixels=3000,
            close_iterations=0,
            open_iterations=0,
            fill_holes=False,
            velocity_rescue_reflectivity_dbz=15.0,
            velocity_rescue_contrast_kt=8.0,
            velocity_rescue_gradient_ktkm=6.0,
        ),
        velocity=velocity_ms,
    )

    assert len(objects) == 1
    obj = objects[0]
    assert obj["max_reflectivity_dbz"] == 18.0
    assert obj["velocity_rescue"] is True
    assert obj["velocity_mean_kt"] > 20.0
    assert obj["velocity_contrast_kt"] >= 8.0
