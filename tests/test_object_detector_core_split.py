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


def test_detector_keeps_nearby_embedded_cores_together():
    field=np.zeros((60,80),dtype=float)
    field[25:35,10:70]=28.0
    field[27:33,30:34]=45.0
    field[27:33,36:40]=45.0
    cfg=ObjectDetectionConfig(min_pixels=24,min_peak_separation_px=8)
    objs=detect_reflectivity_objects(field,cfg)
    assert len(objs)==1
