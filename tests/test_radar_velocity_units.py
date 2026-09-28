import numpy as np
import pytest
from processing.radar_features import MS_TO_KT, velocity_object_summary

def test_radial_velocity_mps_is_converted_to_knots():
    result=velocity_object_summary([0.0, 10.0, -10.0], input_units='m/s')
    assert result['velocity_mean_kt']==pytest.approx(0.0)
    assert result['velocity_p90_abs_kt']==pytest.approx(10.0*MS_TO_KT, rel=1e-6)

def test_velocity_gradient_converts_with_same_factor():
    result=velocity_object_summary([1.0, 2.0], gradient=np.array([1.0,2.0]), input_units='m/s')
    assert result['velocity_gradient_ktkm']==pytest.approx(1.5*MS_TO_KT, rel=1e-6)
