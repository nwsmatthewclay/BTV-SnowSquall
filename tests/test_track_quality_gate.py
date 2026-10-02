import pandas as pd

from processing.object_tracker import CentroidTracker, TrackerConfig
from scripts.build_object_track_catalog import build_track_catalog
from scripts.track_quality_gate import apply_track_quality_gate


def obj(row, column, area=25, z=35):
    return {
        "row_centroid": row,
        "column_centroid": column,
        "pixel_count": area,
        "area_km2": float(area),
        "max_reflectivity_dbz": float(z),
    }


def test_velocity_consistency_preserves_two_parallel_tracks():
    tracker = CentroidTracker(
        TrackerConfig(max_pixel_distance=12, max_time_gap_minutes=10)
    )
    first = tracker.update(
        "2026-01-01T00:00:00Z",
        [obj(0, 0), obj(0, 10)],
    )
    first_ids = {
        x["column_centroid"]: x["object_id"]
        for x in first
    }

    second = tracker.update(
        "2026-01-01T00:05:00Z",
        [obj(0, 2), obj(0, 8)],
    )
    second_ids = {
        x["column_centroid"]: x["object_id"]
        for x in second
    }
    assert second_ids[2.0] == first_ids[0.0]
    assert second_ids[8.0] == first_ids[10.0]

    third = tracker.update(
        "2026-01-01T00:10:00Z",
        [obj(0, 4), obj(0, 6)],
    )
    third_ids = {
        x["column_centroid"]: x["object_id"]
        for x in third
    }
    assert third_ids[4.0] == first_ids[0.0]
    assert third_ids[6.0] == first_ids[10.0]


def test_equal_cost_merge_candidate_is_marked_ambiguous():
    tracker = CentroidTracker(
        TrackerConfig(max_pixel_distance=12, ambiguous_margin=0.12)
    )
    first = tracker.update(
        "2026-01-01T00:00:00Z",
        [obj(0, 0), obj(0, 10)],
    )
    ids = {x["column_centroid"]: x["object_id"] for x in first}

    out = tracker.update(
        "2026-01-01T00:05:00Z",
        [obj(0, 5)],
    )[0]

    assert out["object_id"] == min(ids.values())
    assert out["track_competing_track_count"] == 2
    assert out["track_merge_candidate"]
    assert out["track_association_ambiguous"]
    assert out["track_association_margin"] == 0.0


def test_tracker_emits_velocity_and_radar_mismatch_diagnostics():
    tracker = CentroidTracker()
    radar = {
        "radar_motion_row_per_min": 0.0,
        "radar_motion_column_per_min": 0.5,
        "radar_motion_confidence": 1.0,
    }
    tracker.update(
        "2026-01-01T00:00:00Z",
        [obj(10, 10)],
        radar_motion=radar,
    )
    out = tracker.update(
        "2026-01-01T00:05:00Z",
        [obj(10, 12)],
        radar_motion=radar,
    )[0]
    assert out["track_velocity_mismatch_kt"] >= 0
    assert out["track_radar_motion_mismatch_kt"] >= 0
    assert 0 <= out["track_association_confidence"] <= 1


def test_good_track_passes_quality_gate():
    rows = [
        {
            "population": "positive",
            "case_id": "CASE-A",
            "radar_site": "KCXX",
            "object_id": 1,
            "scan_time_utc": "2026-01-01T00:00:00Z",
            "centroid_lat": 44.0,
            "centroid_lon": -73.0,
            "max_reflectivity_dbz": 30,
            "mean_reflectivity_dbz": 24,
            "area_km2": 20,
            "aspect_ratio": 2.0,
            "geometry_wkt": "POINT(0 0)",
            "track_association_status": "new",
            "track_association_cost": None,
            "track_association_normalized_distance": None,
            "track_association_ambiguous": False,
            "track_merge_candidate": False,
            "track_split_candidate": False,
            "touches_grid_edge": False,
            "motion_speed_kt": None,
        },
        {
            "population": "positive",
            "case_id": "CASE-A",
            "radar_site": "KCXX",
            "object_id": 1,
            "scan_time_utc": "2026-01-01T00:05:00Z",
            "centroid_lat": 44.02,
            "centroid_lon": -73.0,
            "max_reflectivity_dbz": 32,
            "mean_reflectivity_dbz": 25,
            "area_km2": 22,
            "aspect_ratio": 2.1,
            "geometry_wkt": "POINT(0 0)",
            "track_association_status": "matched",
            "track_association_cost": 0.20,
            "track_association_normalized_distance": 0.25,
            "track_association_ambiguous": False,
            "track_merge_candidate": False,
            "track_split_candidate": False,
            "touches_grid_edge": False,
            "motion_speed_kt": 18,
        },
        {
            "population": "positive",
            "case_id": "CASE-A",
            "radar_site": "KCXX",
            "object_id": 1,
            "scan_time_utc": "2026-01-01T00:10:00Z",
            "centroid_lat": 44.04,
            "centroid_lon": -73.0,
            "max_reflectivity_dbz": 34,
            "mean_reflectivity_dbz": 26,
            "area_km2": 24,
            "aspect_ratio": 2.2,
            "geometry_wkt": "POINT(0 0)",
            "track_association_status": "matched",
            "track_association_cost": 0.18,
            "track_association_normalized_distance": 0.20,
            "track_association_ambiguous": False,
            "track_merge_candidate": False,
            "track_split_candidate": False,
            "touches_grid_edge": False,
            "motion_speed_kt": 20,
        },
    ]
    objects = pd.DataFrame(rows)
    catalog = build_track_catalog(objects)
    assert catalog.iloc[0]["quality_tier"] == "pass"
    assert catalog.iloc[0]["quality_score"] >= 75

    accepted, rejected, enriched, _ = apply_track_quality_gate(
        objects, catalog, min_score=75
    )
    assert len(accepted) == 3
    assert len(rejected) == 0
    assert set(enriched["track_quality_gate"]) == {"pass"}


def test_singleton_or_ambiguous_track_does_not_enter_clean_population():
    rows = [
        {
            "population": "null",
            "null_id": "NULL-1",
            "radar_site": "KTYX",
            "object_id": 7,
            "scan_time_utc": "2026-01-01T00:00:00Z",
            "centroid_lat": 44.0,
            "centroid_lon": -75.0,
            "max_reflectivity_dbz": 35,
            "mean_reflectivity_dbz": 25,
            "area_km2": 30,
            "aspect_ratio": 1.5,
            "geometry_wkt": "POINT(0 0)",
            "track_association_status": "new",
            "touches_grid_edge": False,
            "motion_speed_kt": None,
        }
    ]
    objects = pd.DataFrame(rows)
    catalog = build_track_catalog(objects)
    assert catalog.iloc[0]["quality_tier"] in {"review", "reject"}

    accepted, rejected, _, _ = apply_track_quality_gate(
        objects, catalog, min_score=75
    )
    assert accepted.empty
    assert len(rejected) == 1
