from datetime import datetime, timezone

import pandas as pd

from scripts.build_historical_dataset import choose_case


def test_choose_case_uses_nearest_verified_onset():
    cases = pd.DataFrame([
        {
            "case_id": "A",
            "event_start_dt": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        },
        {
            "case_id": "B",
            "event_start_dt": datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        },
    ]).set_index("case_id")

    result = choose_case(datetime(2026, 1, 1, 0, 50, tzinfo=timezone.utc), cases)
    assert result[1] == "B"


def test_choose_case_rejects_distant_scan():
    cases = pd.DataFrame([
        {
            "case_id": "A",
            "event_start_dt": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        },
    ]).set_index("case_id")

    assert choose_case(datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc), cases) is None

def test_environment_fields_are_canonicalized():
    from processing.environment import canonicalize_environment_fields

    result = canonicalize_environment_fields(
        "RAP",
        {
            "cape_jkg": 120.0,
            "cin_jkg": -40.0,
            "shear_0_6km_ms": 10.0,
            "visibility_m": 1609.344,
            "temperature_2m_k": 270.0,
        },
    )

    assert result["sbcape_jkg"] == 120.0
    assert result["sbcin_jkg"] == -40.0
    assert result["shear_0_6km_kt"] > 19.4
    assert result["visibility_sm"] == 1.0
    assert result["temperature_2m_k"] == 270.0



def test_environment_boundary_rejects_future_analysis():
    from datetime import timedelta
    import pytest
    from processing.environment import extract_features

    radar_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    future = radar_time + timedelta(hours=1)

    with pytest.raises(ValueError, match="future RUC environment analysis"):
        extract_features("RUC", None, 44.0, -73.0, radar_time, future)
\n\ndef test_environment_attachment_records_provider_failure_instead_of_aborting(tmp_path, monkeypatch):
    from scripts import build_historical_dataset as mod

    objects = tmp_path / "objects.csv"
    cases = tmp_path / "cases.csv"
    output = tmp_path / "out.csv"

    import pandas as pd
    pd.DataFrame([{
        "case_id": "CASE1",
        "scan_time_utc": "2006-02-24T15:10:00Z",
        "radar_site": "KCXX",
        "object_id": 1,
        "centroid_lat": 44.47,
        "centroid_lon": -73.15,
    }]).to_csv(objects, index=False)
    pd.DataFrame([{
        "case_id": "CASE1",
        "event_start_utc": "2006-02-24T15:10:00Z",
        "source_study": "test",
        "observing_station": "KBTV",
        "peak_wind_kt": 30,
        "min_visibility_km": 0.2,
        "hybrid_case": False,
        "lat": 44.47,
        "lon": -73.15,
    }]).to_csv(cases, index=False)

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(mod, "acquire_for_radar_time", boom)
    mod.enrich(
        objects, output, cases,
        tmp_path / "RAP", tmp_path / "RUC", tmp_path / "NARR"
    )
    result = pd.read_csv(output)
    assert len(result) == 1
    assert result.loc[0, "environment_status"] == "unavailable"
    assert "synthetic provider failure" in result.loc[0, "environment_error"]
