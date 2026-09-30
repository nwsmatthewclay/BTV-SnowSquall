from scripts.probability_postprocess import monotone_cumulative_probabilities


def test_probability_projection_is_cumulative_and_nonnegative():
    result = monotone_cumulative_probabilities({'15':0.60,'30':0.40,'45':0.70,'60':0.65})
    cumulative = result["cumulative"]
    interval = result["interval"]
    assert [cumulative[str(h)] for h in (15,30,45,60)] == sorted(cumulative[str(h)] for h in (15,30,45,60))
    assert all(v >= 0 for v in interval.values())
    assert cumulative["60"] >= cumulative["15"]
