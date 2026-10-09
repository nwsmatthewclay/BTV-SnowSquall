from pathlib import Path

def test_live_publisher_contract():
    root=Path(__file__).resolve().parents[1]
    text=(root/'.github/workflows/live-object-publisher.yml').read_text(encoding='utf-8')
    assert 'cron: "*/5 * * * *"' in text
    assert 'ref: snow-squall-model-foundation' in text
    assert '--radar KCXX' in text
    assert '--radar KTYX' in text
    assert 'KCXX_state.json' in text and 'KTYX_state.json' in text
    assert 'KCXX_objects.geojson' in text and 'KTYX_objects.geojson' in text
    assert 'Restore prior live feed history' in text
    assert 'git push --force origin HEAD:snow-squall-live-data' in text
    assert 'snow-squall-live-data' in text


def test_live_normalization_emits_strict_json_for_nonfinite_values():
    import json
    from scripts.normalize_live_products import json_safe

    payload=json_safe({"nan": float("nan"), "inf": float("inf"), "neg_inf": float("-inf"), "ok": 2.0})
    encoded=json.dumps(payload, allow_nan=False)
    assert 'NaN' not in encoded and 'Infinity' not in encoded
    assert json.loads(encoded)["nan"] is None


def test_live_history_clean_rejects_nonfinite_values():
    from scripts.append_live_object_history import _clean

    assert _clean(float("nan")) is None
    assert _clean(float("inf")) is None
    assert _clean(float("-inf")) is None
    assert _clean(12.5) == 12.5


def test_ktyx_companion_uses_closest_scan_even_if_slightly_newer(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from scripts import process_live_event

    target = datetime(2026, 10, 9, 17, 56, 44, tzinfo=timezone.utc)
    older = ("KTYX20261009_174900_V06", target - timedelta(minutes=7, seconds=43))
    newer = ("KTYX20261009_175739_V06", target + timedelta(seconds=55))
    monkeypatch.setattr(
        process_live_event,
        "find_recent_volumes",
        lambda *args, **kwargs: [older, newer],
    )

    selected = process_live_event.choose_ktyx(
        object(), target, max_age_minutes=8.0, raw_root=None
    )

    assert selected == newer
