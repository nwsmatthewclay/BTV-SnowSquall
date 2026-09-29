from pathlib import Path

from scripts.normalize_live_products import normalize_timestamp, normalize_object


def test_normalize_timestamp_adds_explicit_utc():
    assert normalize_timestamp("2026-09-29T02:00:58.756000") == "2026-09-29T02:00:58.756000Z"
    assert normalize_timestamp("2026-09-29T02:00:58.756000+00:00") == "2026-09-29T02:00:58.756000Z"


def test_normalize_object_only_rewrites_utc_timestamp_fields():
    raw = {
        "timestamp": "2026-09-29T02:00:58.756000",
        "environment_valid_time_utc": "2026-09-29T01:00:00+00:00",
        "source_file": "KCXX20260929_020058_V06",
        "value": 42,
    }
    out = normalize_object(raw)
    assert out["timestamp"].endswith("Z")
    assert out["environment_valid_time_utc"].endswith("Z")
    assert out["source_file"] == raw["source_file"]
    assert out["value"] == 42
