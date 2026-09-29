from pathlib import Path


def test_live_viewer_references_operational_feed_assets():
    root = Path(__file__).resolve().parents[1]
    html = (root / "viewer/live.html").read_text(encoding="utf-8")
    js = (root / "viewer/live.js").read_text(encoding="utf-8")

    assert "live.js" in html
    assert "KCXX" in js and "KTYX" in js
    assert "_objects.geojson" in js
    assert "_history.json" in js
    assert "probability scoring disabled" in html.lower()
    assert (
        "raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/"
        "snow-squall-model-foundation/viewer/data/live/"
    ) in js


def test_live_history_wiring_and_utc_normalization_are_present():
    root = Path(__file__).resolve().parents[1]
    worker = (root / "scripts/live_object_worker.py").read_text(encoding="utf-8")
    processor = (root / "scripts/process_live_volume.py").read_text(encoding="utf-8")
    audit = (root / "scripts/audit_operational_readiness.py").read_text(encoding="utf-8")

    assert "--history-jsonl" in worker
    assert "--history-csv" in worker
    assert "history_jsonl_path=history_jsonl" in worker
    assert "history_csv_path=history_csv" in worker

    assert "--history-jsonl" in processor
    assert "--history-csv" in processor
    assert "history_jsonl_path or Path" in processor
    assert "history_csv_path or Path" in processor
    assert 'replace("+00:00", "Z")' in processor

    assert "--max-age-minutes" in audit
    assert "age_minutes" in audit
