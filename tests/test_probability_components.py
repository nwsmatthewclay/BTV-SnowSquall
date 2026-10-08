from scripts.probability_components import horizon_component_scores


def test_component_scores_are_0_to_100_and_weight_to_100():
    record = {
        "max_reflectivity_dbz": 40.0,
        "reflectivity_contrast_db": 9.0,
        "reflectivity_gradient_p90_dbkm": 6.0,
        "velocity_contrast_kt": 18.0,
        "core_fraction": 0.30,
        "reflectivity_trend_dbz_per_hr": 5.0,
        "aspect_ratio": 2.5,
        "track_age_scans": 4,
        "cape_jkg": 35.0,
        "mean_rh_0_2km_pct": 72.0,
        "thetae_delta_0_2km_k": 2.0,
        "mean_wind_0_2km_ms": 10.5,
        "lapse_rate_0_3km_c_km": 6.7,
        "snsq": 0.8,
    }

    result = horizon_component_scores(record)

    assert set(result["probabilities"]) == {15, 30, 45, 60}
    for horizon in (15, 30, 45, 60):
        components = result["components"][horizon]
        assert 0 <= components["radar"] <= 100
        assert 0 <= components["environment"] <= 100
        assert 0 <= components["analog"] <= 100
        assert components["weights"] == {
            "radar": 0.50,
            "environment": 0.50,
            "analog": 0.00,
        }
        expected = (
            components["radar"] * 0.50
            + components["environment"] * 0.50
            + components["analog"] * 0.00
        )
        assert abs(result["probabilities"][horizon] - round(expected, 2)) < 1e-9
        assert 0 <= result["probabilities"][horizon] <= 100


def test_unavailable_analog_is_explicitly_neutral():
    result = horizon_component_scores({"max_reflectivity_dbz": 30.0})
    assert result["analog"]["score"] == 50.0
    assert result["analog"]["detail"]["status"] == "provisional_neutral"
