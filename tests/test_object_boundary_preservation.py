import numpy as np
from processing.object_detector import ObjectDetectionConfig, detect_reflectivity_objects

def test_boundary_echo_survives_cleanup_and_is_flagged():
    field=np.zeros((30,30),dtype=float)
    field[0:5,0:6]=30.0
    objs=detect_reflectivity_objects(field)
    assert len(objs)==1
    assert objs[0]["touches_grid_edge"] is True
    assert objs[0]["pixel_count"]>=24
