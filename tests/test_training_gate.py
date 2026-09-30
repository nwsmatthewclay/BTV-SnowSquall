import pandas as pd

from scripts.train_baseline_model import prepare_dataset


def _schema():
    return {
        "predictor_columns": ["area_km2"],
        "operational_predictor_columns": ["area_km2"],
    }


def _null(case_id):
    return {
        "population": "winter_null_candidate",
        "null_id": case_id,
        "case_id": "",
        "activity_class": "quiet",
        "label_status": "unlabeled",
        "track_event_associated": False,
        "area_km2": 5.0,
        "squall_onset_within_15m": 0,
    }


def test_trainer_excludes_case_rows_without_supervised_provenance():
    rows = [
        {
            "population": "verified_case_context",
            "case_id": "CASE_BAD",
            "null_id": "",
            "supervision_class": "unverified_case",
            "label_status": "prospective_positive",
            "track_event_associated": True,
            "area_km2": 12.0,
            "squall_onset_within_15m": 1,
        },
        _null("N1"),
        _null("N2"),
        _null("N3"),
    ]
    frame = pd.DataFrame(rows)
    usable, predictors = prepare_dataset(frame, _schema(), "squall_onset_within_15m")

    assert predictors == ["area_km2"]
    assert "CASE_BAD" not in set(usable["case_id"].astype(str))
    assert usable["population"].eq("winter_null_candidate").all()


def test_trainer_accepts_explicit_supervised_provenance():
    rows = [
        {
            "population": "verified_case_context",
            "case_id": "CASE_GOOD",
            "null_id": "",
            "supervision_class": "supervised_positive",
            "label_status": "prospective_positive",
            "track_event_associated": True,
            "area_km2": 12.0,
            "squall_onset_within_15m": 1,
        },
        _null("N1"),
        _null("N2"),
        _null("N3"),
    ]
    frame = pd.DataFrame(rows)
    usable, _ = prepare_dataset(frame, _schema(), "squall_onset_within_15m")

    assert "CASE_GOOD" in set(usable["case_id"].astype(str))
    assert usable["squall_onset_within_15m"].sum() == 1
