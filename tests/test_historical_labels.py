import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from scripts.label_historical_outcomes import build_labels


def test_historical_labels_accept_namedtuple_case_rows(tmp_path):
    cases = pd.DataFrame([{
        "case_id": "CASE1",
        "event_start_utc": "2006-02-07T12:00:00Z",
        "observing_station": "KBTV",
        "vis_below_0p8_min": 30,
    }])
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)

    objects = pd.DataFrame([{
        "object_id": "KCXX_1",
        "scan_time_utc": "2006-02-07T11:45:00Z",
        "case_id": "CASE1",
        "centroid_lat": 44.47,
        "centroid_lon": -73.15,
    }])

    result = build_labels(objects, Path(cases_path))

    assert result.loc[0, "squall_onset_within_15m"] == 1
    assert result.loc[0, "label_status"] == "prospective_positive"
