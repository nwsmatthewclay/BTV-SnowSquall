import pandas as pd
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
    assert bool(result.loc[0, "track_event_associated"])


def test_track_association_rejects_unrelated_object(tmp_path):
    cases = pd.DataFrame([{
        "case_id": "TEST",
        "observing_station": "KBTV",
        "event_start_utc": "2020-01-01T12:00:00Z",
        "vis_below_0p8_min": 30,
    }])
    path = tmp_path / "cases.csv"
    cases.to_csv(path, index=False)

    rows = [
        {
            "case_id": "TEST", "object_id": "A",
            "scan_time_utc": "2020-01-01T11:50:00Z",
            "centroid_lat": 44.5, "centroid_lon": -73.2,
        },
        {
            "case_id": "TEST", "object_id": "A",
            "scan_time_utc": "2020-01-01T12:00:00Z",
            "centroid_lat": 44.48, "centroid_lon": -73.16,
        },
        {
            "case_id": "TEST", "object_id": "B",
            "scan_time_utc": "2020-01-01T12:00:00Z",
            "centroid_lat": 44.60, "centroid_lon": -73.15,
        },
    ]

    result = build_labels(pd.DataFrame(rows), Path(path))
    a = result[result["object_id"] == "A"].iloc[0]
    b = result[result["object_id"] == "B"].iloc[0]

    assert bool(a["track_event_associated"])
    assert b["label_status"] == "unassociated_object"


def test_only_nearest_track_per_radar_is_event_associated(tmp_path):
    cases = pd.DataFrame([{
        "case_id": "TEST",
        "observing_station": "KBTV",
        "event_start_utc": "2020-01-01T12:00:00Z",
        "vis_below_0p8_min": 30,
    }])
    path = tmp_path / "cases.csv"
    cases.to_csv(path, index=False)

    rows = [
        {
            "case_id": "TEST", "radar_site": "KCXX", "object_id": "NEAR",
            "scan_time_utc": "2020-01-01T11:55:00Z",
            "centroid_lat": 44.48, "centroid_lon": -73.16,
        },
        {
            "case_id": "TEST", "radar_site": "KCXX", "object_id": "FAR",
            "scan_time_utc": "2020-01-01T11:55:00Z",
            "centroid_lat": 44.60, "centroid_lon": -73.15,
        },
    ]

    result = build_labels(pd.DataFrame(rows), Path(path))
    near = result[result["object_id"] == "NEAR"].iloc[0]
    far = result[result["object_id"] == "FAR"].iloc[0]

    assert bool(near["track_event_associated"])
    assert not bool(far["track_event_associated"])
    assert far["label_status"] == "unassociated_object"
