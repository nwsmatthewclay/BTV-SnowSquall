from processing.snsq import snow_squall_parameter


def test_snsq_favorable_environment():
    result = snow_squall_parameter(
        mean_rh_0_2km_pct=75.0,
        thetae_delta_0_2km_k=0.0,
        mean_wind_0_2km_ms=9.0,
        wetbulb_2m_c=0.0,
    )

    assert result["snsq"] == 1.0
    assert result["moisture_factor"] == 1.0
    assert result["instability_factor"] == 1.0
    assert result["wind_factor"] == 1.0
    assert result["snow_temperature_pass"] is True


def test_snsq_negative_ingredients_are_floored():
    result = snow_squall_parameter(
        mean_rh_0_2km_pct=50.0,
        thetae_delta_0_2km_k=6.0,
        mean_wind_0_2km_ms=3.0,
        wetbulb_2m_c=0.0,
    )
    assert result["snsq"] == 0.0
    assert result["moisture_factor"] == 0.0
    assert result["instability_factor"] == 0.0


def test_snsq_warm_surface_zeroes_parameter():
    result = snow_squall_parameter(
        mean_rh_0_2km_pct=75.0,
        thetae_delta_0_2km_k=0.0,
        mean_wind_0_2km_ms=9.0,
        wetbulb_2m_c=1.1,
    )
    assert result["snsq"] == 0.0
    assert result["snow_temperature_pass"] is False


def test_snsq_missing_inputs_stay_missing():
    result = snow_squall_parameter(
        mean_rh_0_2km_pct=None,
        thetae_delta_0_2km_k=0.0,
        mean_wind_0_2km_ms=9.0,
    )
    assert result["snsq"] is None
