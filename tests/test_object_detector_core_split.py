import numpy as np
from processing.object_detector import detect_reflectivity_objects, ObjectDetectionConfig

def test_detector_preserves_single_core_band():
    field=np.zeros((60,80),dtype=float)
    field[25:35,10:70]=28.0
    field[28:32,35:45]=42.0
    objs=detect_reflectivity_objects(field,ObjectDetectionConfig(min_pixels=24))
    assert len(objs)==1

def test_detector_splits_two_embedded_cores():
    field=np.zeros((60,80),dtype=float)
    field[25:35,10:70]=28.0
    field[27:33,20:28]=45.0
    field[27:33,52:60]=45.0
    objs=detect_reflectivity_objects(field,ObjectDetectionConfig(min_pixels=24))
    assert len(objs)==2
