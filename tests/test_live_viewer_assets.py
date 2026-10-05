from pathlib import Path


def test_live_viewer_references_operational_feed_assets():
    root = Path(__file__).resolve().parents[1]
    html = (root / "viewer/live.html").read_text(encoding="utf-8")
    js = (root / "viewer/live.js").read_text(encoding="utf-8")

    assert "live.js" in html
    assert "KCXX" in js and "KTYX" in js
    assert "_objects.geojson" in js
    assert 'fetch(base+site+"_objects.geojson?cb="+Date.now()' in js
    assert 'fetch(base+site+"_state.json?cb="+Date.now()' in js
    assert 'fetchOptional(base+site+"_history.json?cb="+Date.now(),[])' in js
    # Current viewer builds explicit radar feed filenames rather than a generic .json suffix.
    assert "probability scoring disabled" in html.lower()
    assert "detail-drawer" in html
    assert "selectedSummary" in html
    assert "raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/" in js
    assert "snow-squall-live-data/viewer/data/live/" in js


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



def test_live_feed_isolated_from_model_branch():
    root = Path(__file__).resolve().parents[1]
    js = (root / "viewer/live.js").read_text(encoding="utf-8")
    workflow = (
        root / ".github" / "workflows" / "live-object-publisher.yml"
    ).read_text(encoding="utf-8")

    assert "snow-squall-live-data/viewer/data/live/" in js
    assert "snow-squall-live-data" in workflow
    assert "HEAD:snow-squall-model-foundation" not in workflow


def test_object_dataset_pilot_uses_latest_run_for_science_branch():
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github" / "workflows" / "object-dataset-pilot.yml"
    ).read_text(encoding="utf-8")
    assert "cancel-in-progress: true" in workflow


def test_live_viewer_degrades_per_radar_without_taking_down_other_feed():
    root = Path(__file__).resolve().parents[1]
    js = (root / "viewer/live.js").read_text(encoding="utf-8")
    assert 'return {site:site,error:String(e.message||e)' in js
    assert 'got.map(function(x){return [x.site,x]})' in js
    assert 'got.filter(function(x){return x.error||ageMinutes' in js


def test_live_viewer_consumes_radar_health_status():
    root = Path(__file__).resolve().parents[1]
    js = (root / "viewer/live.js").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "live-object-publisher.yml").read_text(encoding="utf-8")
    assert 'fetchOptional(base+site+"_health.json?cb="+Date.now(),null)' in js
    assert "Restore prior live feed history" in workflow
    assert "Build bounded browser history payloads" in workflow
    assert "Validate KCXX live product" in workflow

# CI trigger: final live viewer contract alignment.
