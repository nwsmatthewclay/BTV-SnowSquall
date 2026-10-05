import pandas as pd

from scripts.train_baseline_model import prepare_dataset


def _schema():
    return {
        "predictor_columns": ["area_km2"],
        "operational_predictor_columns": ["area_km2"],
    }


def _contract(row):
    return {
        **row,
        "base_reflectivity_mean_dbz": 18.0,
        "base_reflectivity_max_dbz": 35.0,
        "base_reflectivity_p90_dbz": 28.0,
        "base_velocity_mean_kt": 5.0,
        "base_velocity_std_kt": 3.0,
        "base_velocity_p90_abs_kt": 9.0,
        "base_reflectivity_valid_fraction": 0.5,
        "base_velocity_valid_fraction": 0.5,
        "cape_jkg": 120.0,
        "pwat_mm": 12.0,
        "temperature_2m_k": 268.0,
        "dewpoint_2m_k": 265.0,
        "rh_2m_pct": 82.0,
        "u10_ms": 4.0,
        "v10_ms": -2.0,
        "velocity_mean_kt": 20.0,
        "velocity_std_kt": 4.0,
        "velocity_p90_abs_kt": 25.0,
    }


def _null(case_id):
    return _contract({
        "population": "winter_null_candidate",
        "null_id": case_id,
        "case_id": "",
        "activity_class": "quiet",
        "label_status": "unlabeled",
        "track_event_associated": False,
        "area_km2": 5.0,
        "squall_onset_within_15m": 0,
    })


def test_trainer_excludes_case_rows_without_supervised_provenance():
    rows = [
        _contract({
            "population": "verified_case_context",
            "case_id": "CASE_BAD",
            "null_id": "",
            "supervision_class": "unverified_case",
            "label_status": "prospective_positive",
            "track_event_associated": True,
            "area_km2": 12.0,
            "squall_onset_within_15m": 1,
        }),
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
        _contract({
            "population": "verified_case_context",
            "case_id": "CASE_GOOD",
            "null_id": "",
            "supervision_class": "supervised_positive",
            "label_status": "prospective_positive",
            "track_event_associated": True,
            "area_km2": 12.0,
            "squall_onset_within_15m": 1,
        }),
        _null("N1"),
        _null("N2"),
        _null("N3"),
    ]
    frame = pd.DataFrame(rows)
    usable, _ = prepare_dataset(frame, _schema(), "squall_onset_within_15m")

    assert "CASE_GOOD" in set(usable["case_id"].astype(str))
    assert usable["squall_onset_within_15m"].sum() == 1


def test_case_heldout_folds_keep_positive_and_null_groups_separate():
    import pandas as pd
    from scripts.train_case_heldout_models import event_folds

    groups = pd.Series([
        "case:A", "case:A",
        "case:B", "case:B",
        "case:C", "case:C",
        "null:N1", "null:N1",
        "null:N2", "null:N2",
        "null:N3", "null:N3",
    ])
    y = pd.Series([1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    folds = event_folds(groups, y, n_splits=3)
    assert folds
    flattened = [item for fold in folds for item in fold]
    assert sorted(flattened) == sorted(groups.unique())
    assert not set(groups[ y.eq(1) ]) & set(groups[ y.eq(0) ])
