import numpy as np

from processing.snsq import snow_squall_parameter
from processing.snsq_profile import build_snsq_profile


def test_snsq_reference_conditions_equal_one():
    result = snow_squall_parameter(75.0, 0.0, 9.0, wetbulb_2m_c=0.0)
    assert result['snsq'] == 1.0
    assert result['snow_temperature_pass'] is True


def test_snsq_warm_surface_is_zero():
    result = snow_squall_parameter(75.0, 0.0, 9.0, wetbulb_2m_c=1.1)
    assert result['snsq'] == 0.0
    assert result['snow_temperature_pass'] is False


def test_snsq_profile_uses_zero_to_two_km_mean():
    heights=np.array([100.,500.,1000.,1500.,2000.,2200.])
    pressure=np.array([990.,950.,900.,850.,800.,780.])
    rh=np.array([75.,75.,75.,75.,75.,99.])
    temp=np.array([273.,270.,267.,264.,260.,258.])
    dpt=np.array([270.,267.,264.,261.,257.,255.])
    u=np.ones(6)*9.
    v=np.zeros(6)
    result=build_snsq_profile(
        heights,pressure,temp,dpt,rh,u,v,
        1000.,273.,270.,surface_rh_pct=75.,surface_u_ms=9.,surface_v_ms=0.,wetbulb_2m_c=0.
    )
    assert result['mean_rh_0_2km_pct'] == 75.0
    assert abs(result['mean_wind_0_2km_ms']-9.0) < 1e-6
    assert result['snsq'] is not None