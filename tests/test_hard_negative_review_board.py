import pandas as pd

from scripts.build_hard_negative_review_board import build


def test_review_board_contains_key_hard_negative_fields(tmp_path):
    packet = pd.DataFrame({
        "null_id": ["N1"],
        "hard_negative_score": [6],
        "review_status": ["pending"],
        "final_class": ["pending"],
        "radars": ["KCXX,KTYX"],
        "peak_radar_site": ["KCXX"],
        "peak_scan_time_utc": ["2026-01-01T00:30:00Z"],
        "peak_object_id": ["KCXX_001"],
        "max_reflectivity_dbz": [42.0],
        "surface_min_visibility_m": [650.0],
        "surface_snow_reports": [2],
        "review_reasons": ["nearby_surface_snow_report"],
    })
    out = tmp_path / "review.html"
    build(packet, out)
    text = out.read_text(encoding="utf-8")

    assert "BTV Snow Squall Hard-Negative Review Board" in text
    assert "N1" in text
    assert "KCXX_001" in text
    assert "nearby_surface_snow_report" in text
