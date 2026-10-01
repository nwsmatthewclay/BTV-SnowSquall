from processing.radar_storm_motion import attach_radar_storm_motion
import numpy as np

def test_radar_motion_outputs_vector_components():
    a=np.zeros((40,40)); a[15:20,10:15]=45
    b=np.zeros_like(a); b[15:20,13:18]=45
    m=attach_radar_storm_motion(a,b,5,spacing_km=1,max_shift_km=15)
    assert np.isfinite(m["radar_motion_u_kt"])
    assert abs(m["radar_motion_u_kt"]) > 0
