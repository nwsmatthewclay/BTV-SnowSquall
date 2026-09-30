import pandas as pd

from scripts.score_independent_validation import expected_calibration_error


def test_expected_calibration_error_zero_for_perfectly_calibrated_bins():
    y = pd.Series([0, 0, 1, 1])
    p = pd.Series([0.25, 0.25, 0.75, 0.75])
    ece, bins = expected_calibration_error(y, p, bins=2)
    assert ece == 0.0
    assert len(bins) == 2
