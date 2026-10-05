import numpy as np
import pandas as pd

from src.snow_squall.training import case_scan_balanced_weights


def test_case_scan_weights_equalize_cases_and_scans():
    d = pd.DataFrame({
        "case_id": ["A", "A", "A", "B", "B"],
        "scan_time_utc": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-02T00:00:00Z",
            "2026-01-02T00:05:00Z",
        ],
    })
    w = case_scan_balanced_weights(d)
    assert abs(w[:3].sum() - w[3:].sum()) < 1e-9
    assert abs(w[0] - w[1]) < 1e-9
    assert w[2] > w[0]


def test_null_windows_are_balanced_as_independent_groups():
    frame = pd.DataFrame({
        "split_group": [
            "case:A", "case:A", "case:B", "case:B",
            "null:N1", "null:N1", "null:N2", "null:N2",
        ],
        "case_id": ["A", "A", "B", "B", None, None, None, None],
        "null_id": [None, None, None, None, "N1", "N1", "N2", "N2"],
        "scan_time_utc": [
            "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z",
            "2026-01-02T00:00:00Z", "2026-01-02T00:05:00Z",
            "2026-01-03T00:00:00Z", "2026-01-03T00:05:00Z",
            "2026-01-04T00:00:00Z", "2026-01-04T00:05:00Z",
        ],
    })

    weights = case_scan_balanced_weights(frame)
    frame = frame.assign(weight=weights)
    group_totals = frame.groupby("split_group")["weight"].sum()
    np.testing.assert_allclose(
        group_totals.to_numpy(), group_totals.iloc[0], rtol=0, atol=1e-12
    )


def test_fallback_uses_null_id_when_split_group_is_missing():
    frame = pd.DataFrame({
        "case_id": [None, None, None, "A", "A"],
        "null_id": ["N1", "N1", "N2", None, None],
        "scan_time_utc": pd.to_datetime(
            [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:05:00Z",
                "2026-01-02T00:00:00Z",
                "2026-01-03T00:00:00Z",
                "2026-01-03T00:05:00Z",
            ],
            utc=True,
        ),
    })

    weights = case_scan_balanced_weights(frame)
    groups = pd.Series(["N1", "N1", "N2", "A", "A"], name="group")
    totals = pd.DataFrame({"group": groups, "w": weights}).groupby("group")["w"].sum()
    np.testing.assert_allclose(
        totals.to_numpy(), totals.iloc[0], rtol=0, atol=1e-12
    )
