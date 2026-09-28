import json

import pandas as pd

from scripts.build_pilot_report import main as build_report_main


def test_pilot_report_renders_population_and_baseline_tables(tmp_path, monkeypatch):
    pos = pd.DataFrame([
        {
            "case_id": "BTV20060224",
            "radar_site": "KCXX",
            "object_id": 1,
            "label_status": "verified_event_interval",
            "environment_status": "complete",
            "max_reflectivity_dbz": 45.0,
        }
    ])
    null = pd.DataFrame([
        {
            "radar_site": "KCXX",
            "object_id": 2,
            "environment_status": "complete",
        }
    ])
    tracks = pd.DataFrame([{"object_id": 1}, {"object_id": 2}])
    coverage = {
        "group_coverage": [
            {
                "group": "vertical",
                "fields_present": 4,
                "fields_with_values": 4,
                "fields": 4,
                "mean_field_coverage_pct": 98.4,
            }
        ],
        "zero_coverage_fields": [],
    }
    for name, frame in (
        ("positive.csv", pos),
        ("null.csv", null),
        ("positive_tracks.csv", tracks),
        ("null_tracks.csv", tracks),
    ):
        frame.to_csv(tmp_path / name, index=False)

    (tmp_path / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
    (tmp_path / "positive_radar.json").write_text(
        json.dumps({"object_records": 1, "failed_volumes": 0, "reader_backend_volume_counts": {"pyart_legacy_nexrad": 1}}),
        encoding="utf-8",
    )
    (tmp_path / "null_radar.json").write_text(
        json.dumps({"object_records": 1, "failed_volumes": 0, "reader_backend_volume_counts": {"pyart_legacy_nexrad": 1}}),
        encoding="utf-8",
    )

    baseline_dir = tmp_path / "baseline_model_30m"
    baseline_dir.mkdir()
    (baseline_dir / "metrics.json").write_text(
        json.dumps(
            {
                "training_rows": 10,
                "training_groups": 5,
                "positive_case_group_count": 1,
                "evaluation_status": "case_held_out_not_interpretable",
                "metrics": {"auc_roc": None, "average_precision": None, "brier_score": 0.1},
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "report.html"
    argv = [
        "build_pilot_report.py",
        "--positive",
        str(tmp_path / "positive.csv"),
        "--null",
        str(tmp_path / "null.csv"),
        "--positive-tracks",
        str(tmp_path / "positive_tracks.csv"),
        "--null-tracks",
        str(tmp_path / "null_tracks.csv"),
        "--positive-radar-audit",
        str(tmp_path / "positive_radar.json"),
        "--null-radar-audit",
        str(tmp_path / "null_radar.json"),
        "--baseline-root",
        str(tmp_path),
        "--coverage",
        str(tmp_path / "coverage.json"),
        "--output",
        str(output),
    ]
    monkeypatch.setattr("sys.argv", argv)
    build_report_main()

    html = output.read_text(encoding="utf-8")
    assert "Verified-case context" in html
    assert "Winter null candidates" in html
    assert "30m" in html
    assert "98.4" in html
    assert "Baseline readiness warning" in html
    assert "case_held_out_not_interpretable" in html
