import json
from datetime import datetime, timezone

from scripts.live_healthcheck import healthcheck


def test_live_healthcheck_reports_healthy_recent_unscored_product(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    state = {
        "last_source": "KCXX-test",
        "last_scan_time_utc": now,
        "last_object_count": 0,
    }
    geo = {
        "type": "FeatureCollection",
        "features": [],
        "metadata": {
            "probability_status": "not_scored",
            "object_count": 0,
        },
    }
    sp = tmp_path / "state.json"
    gp = tmp_path / "objects.geojson"
    sp.write_text(json.dumps(state), encoding="utf-8")
    gp.write_text(json.dumps(geo), encoding="utf-8")

    report = healthcheck(sp, gp, max_age_minutes=15)
    assert report["status"] == "healthy"
    assert all(report["checks"].values())


def test_live_healthcheck_detects_stale_product(tmp_path):
    old = (datetime.now(timezone.utc) - __import__("datetime").timedelta(minutes=30)).isoformat()
    state = {
        "last_source": "KCXX-test",
        "last_scan_time_utc": old,
        "last_object_count": 0,
    }
    geo = {
        "type": "FeatureCollection",
        "features": [],
        "metadata": {
            "probability_status": "not_scored",
            "object_count": 0,
        },
    }
    sp = tmp_path / "state.json"
    gp = tmp_path / "objects.geojson"
    sp.write_text(json.dumps(state), encoding="utf-8")
    gp.write_text(json.dumps(geo), encoding="utf-8")

    report = healthcheck(sp, gp, max_age_minutes=15)
    assert report["status"] == "degraded"
    assert report["checks"]["fresh_within_threshold"] is False


def test_live_healthcheck_audits_shadow_probability_sequence(tmp_path):
    from scripts.live_healthcheck import audit_shadow_root

    for site in ("KCXX", "KTYX"):
        payload = {
            "mode": "live_shadow_research",
            "operational_release_status": "candidate_only_not_operational",
            "site": site,
            "scored_object_count": 1,
            "records": [{
                "research_probabilities": {
                    "15": 0.20,
                    "30": 0.40,
                    "45": 0.40,
                    "60": 0.70,
                }
            }],
        }
        (tmp_path / f"{site}_shadow.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    report = audit_shadow_root(tmp_path)
    assert report["status"] == "pass"
    assert all(row["probability_count"] == 4 for row in report["sites"])
