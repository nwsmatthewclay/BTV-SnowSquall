from datetime import datetime, timezone

from scripts.discover_snow_squall_cases import merge_candidates, norm_county


def test_norm_county():
    assert norm_county("Saint Lawrence County") == "SAINT LAWRENCE"
    assert norm_county("Essex") == "ESSEX"


def test_merge_cross_source_evidence():
    base = {
        "candidate_id": "A",
        "candidate_source": "IEM_LSR",
        "verification_class": "unverified_report_only",
        "verification_status": "unverified_candidate",
        "event_start_utc": "2024-01-01T15:00:00+00:00",
        "state": "VT", "county": "CHITTENDEN", "lat": 44.5, "lon": -73.2,
        "event_type": "Snow Squall", "event_id": "", "source": "Spotter",
        "narrative": "SNOW SQUALL with whiteout conditions",
        "evidence": "iem_lsr_text", "ncei_explicit_snow_squall": False, "lsr_count": 1,
    }
    ncei = dict(base)
    ncei.update({
        "candidate_id": "B",
        "candidate_source": "NCEI_STORM_EVENTS",
        "verification_class": "official_documented",
        "verification_status": "documented_candidate",
        "event_start_utc": "2024-01-01T15:25:00+00:00",
        "event_id": "123",
        "source": "NWS",
        "evidence": "narrative:snow_squall",
        "ncei_explicit_snow_squall": True,
        "lsr_count": 0,
    })
    cfg = {
        "ncei_match_minutes": 90, "ncei_match_radius_km": 100,
        "lsr_cluster_minutes": 60, "lsr_cluster_radius_km": 75,
        "candidate_buffer_minutes": 90,
    }
    merged = merge_candidates([base, ncei], cfg)
    assert len(merged) == 1
    assert merged[0]["verification_class"] == "official_plus_independent_report"
    assert merged[0]["lsr_count"] == 1


def test_distinct_ncei_events_are_not_collapsed():
    def rec(i, t):
        return {
            "candidate_id": str(i), "candidate_source": "NCEI_STORM_EVENTS",
            "verification_class": "official_documented",
            "verification_status": "documented_candidate",
            "event_start_utc": t, "state": "VT", "county": "CHITTENDEN",
            "lat": 44.5, "lon": -73.2, "event_type": "Snow Squall",
            "event_id": str(i), "source": "NWS", "narrative": "snow squall",
            "evidence": "event_type:snow_squall", "ncei_explicit_snow_squall": True,
            "lsr_count": 0,
        }
    cfg = {
        "ncei_match_minutes": 90, "ncei_match_radius_km": 100,
        "lsr_cluster_minutes": 60, "lsr_cluster_radius_km": 75,
        "candidate_buffer_minutes": 90,
    }
    merged = merge_candidates([
        rec(1, "2024-01-01T15:00:00+00:00"),
        rec(2, "2024-01-01T15:20:00+00:00"),
    ], cfg)
    assert len(merged) == 2
def test_ncei_screening_is_not_verified():
    from scripts.discover_snow_squall_cases import merged_verification_class
    assert merged_verification_class({"NCEI_STORM_EVENTS_SCREENING"}) == "unverified_report_only"
    assert merged_verification_class({"NCEI_STORM_EVENTS_SCREENING", "IEM_COW_SQW"}) == "warning_only"


def test_warning_plus_ncei_explicit_is_official_evidence():
    from scripts.discover_snow_squall_cases import merged_verification_class
    assert merged_verification_class({"NCEI_STORM_EVENTS", "IEM_COW_SQW"}) == "official_plus_warning"


def test_ncei_state_normalization_accepts_full_names():
    from scripts.discover_snow_squall_cases import normalize_state, in_primary_cwa
    assert normalize_state("VERMONT") == "VT"
    assert normalize_state("New York") == "NY"
    cfg = {
        "vt_excluded_counties": ["BENNINGTON", "WINDHAM"],
        "ny_cwa_counties": ["CLINTON", "ESSEX", "FRANKLIN", "ST LAWRENCE"],
    }
    assert in_primary_cwa({"STATE": "VERMONT", "CZ_NAME": "CHITTENDEN"}, cfg)
    assert in_primary_cwa({"STATE": "NEW YORK", "CZ_NAME": "CLINTON"}, cfg)


def test_screening_class_is_explicitly_allowed():
    from scripts.audit_snow_squall_case_ledger import ALLOWED_CLASSES
    assert "official_screening_candidate" in ALLOWED_CLASSES

def test_swdi_ztime_column_is_accepted_by_discovery(monkeypatch):
    import pandas as pd
    import scripts.discover_snow_squall_cases as mod

    frame = pd.DataFrame([{
        "ZTIME": "2024-01-02T12:00:00Z",
        "STATE": "VT",
        "COUNTY": "CHITTENDEN",
        "LAT": 44.5,
        "LON": -73.2,
        "TYPETEXT": "SNOW SQUALL",
        "REMARK": "snow squall",
        "WFO": "BTV",
        "CITY": "Burlington",
        "TYPECODE": "SQ",
        "SOURCE": "NWS",
    }])

    monkeypatch.setattr(mod, "_bulk_year", lambda *args, **kwargs: frame)
    cfg = {
        "start_year": 2024,
        "end_year": 2024,
        "primary_states": ["VT", "NY"],
        "vt_excluded_counties": ["BENNINGTON", "WINDHAM"],
        "ny_cwa_counties": ["CLINTON", "ESSEX", "FRANKLIN", "ST LAWRENCE"],
        "ncei_match_minutes": 90,
        "ncei_match_radius_km": 100,
        "lsr_cluster_minutes": 60,
        "lsr_cluster_radius_km": 75,
        "candidate_buffer_minutes": 90,
        "radars": {"KCXX": [44.511, -73.166], "KTYX": [43.756, -75.680]},
        "radar_max_range_km": 220,
        "max_radars_per_case": 1,
    }
    rows = mod.gather_swdi_plsr(cfg)
    assert len(rows) == 1
    assert rows[0]["candidate_source"] == "SWDI_PLSR"
    assert rows[0]["state"] == "VT"
