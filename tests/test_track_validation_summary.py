import pandas as pd

from scripts.build_track_validation_summary import summarize


def test_real_case_summary_breaks_out_quality_by_case():
    objects = pd.DataFrame(
        {
            "case_id": ["A", "A", "B"],
            "radar_site": ["KCXX", "KCXX", "KTYX"],
            "object_id": [1, 1, 2],
            "track_quality_score": [90, 90, 50],
            "track_association_confidence": [0.9, 0.8, 0.4],
        }
    )
    tracks = pd.DataFrame(
        {
            "case_id": ["A", "B"],
            "radar_site": ["KCXX", "KTYX"],
            "object_id": [1, 2],
            "quality_tier": ["pass", "review"],
            "quality_score": [90, 50],
            "qc_flags": ["", "fewer_than_3_scans"],
            "qc_status": ["pass", "review"],
        }
    )

    report = summarize(objects, tracks)
    assert report["tracks"] == 2
    assert report["case_count"] == 2
    assert report["track_quality_tiers"]["pass"] == 1
    assert report["track_quality_tiers"]["review"] == 1
    assert len(report["case_summary"]) == 2
    assert report["case_summary"][0]["case_id"] == "A"
