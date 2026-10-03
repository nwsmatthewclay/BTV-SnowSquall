
import json
import numpy as np
from pathlib import Path
from scripts.process_live_volume import process_volume


def test_live_product_marks_edge_objects(monkeypatch, tmp_path):
    class FakeRadar:
        pass

    fake = FakeRadar()
    monkeypatch.setattr("scripts.process_live_volume.read_level2", lambda p: fake)
    monkeypatch.setattr(
        "scripts.process_live_volume.volume_metadata",
        lambda radar, path: {"radar_id": "KCXX", "scan_time_utc": "2026-01-01T12:00:00Z"},
    )
    monkeypatch.setattr("scripts.process_live_volume.apply_radar_origin", lambda *a, **k: None)
    monkeypatch.setattr("scripts.process_live_volume.resolve_fields", lambda radar: {"reflectivity": "z"})
    monkeypatch.setattr("scripts.process_live_volume.grid_lowest_sweep", lambda *a, **k: object())
    monkeypatch.setattr("scripts.process_live_volume.grid_field_2d", lambda *a, **k: np.ones((2, 2)))
    monkeypatch.setattr(
        "scripts.process_live_volume.grid_latlon",
        lambda grid: (
            np.array([[44, 44], [44.01, 44.01]]),
            np.array([[-73, -72.99], [-73, -72.99]]),
        ),
    )
    monkeypatch.setattr(
        "scripts.process_live_volume.detect_reflectivity_objects",
        lambda data, velocity=None: [{
            "object_id": 1, "pixel_count": 4, "max_reflectivity_dbz": 30.0,
            "mean_reflectivity_dbz": 25.0, "core_pixel_count": 0,
            "row_centroid": 0.5, "column_centroid": 0.5,
            "row_indices": [0, 0, 1, 1], "column_indices": [0, 1, 0, 1],
            "touches_grid_edge": True,
        }],
    )
    monkeypatch.setattr(
        "scripts.process_live_volume.CentroidTracker",
        lambda *a, **k: __import__("processing.object_tracker", fromlist=["CentroidTracker"]).CentroidTracker(),
    )
    monkeypatch.setattr("scripts.process_live_volume.acquire_for_radar_time", lambda *a, **k: None)
    monkeypatch.setattr(
        "scripts.append_live_object_history.append_history",
        lambda *a, **k: None,
    )

    state = tmp_path / "state.json"
    output = tmp_path / "out.geojson"
    process_volume(Path("KCXX_test"), state, output)
    geo = json.loads(output.read_text())
    props = geo["features"][0]["properties"]
    assert props["touches_grid_edge"] is True
    assert props["data_quality"] == "degraded"


def test_live_object_geometry_repairs_fragmented_polygon_to_polygon():
    from scripts.process_live_volume import object_geometry

    mask = np.zeros((6, 6), dtype=bool)
    mask[1, 1] = True
    mask[4, 4] = True
    lat = np.array([[44 + 0.01*r for c in range(6)] for r in range(6)])
    lon = np.array([[-73 + 0.01*c for c in range(6)] for r in range(6)])
    geometry, area = object_geometry(mask, lat, lon)
    assert geometry is not None
    assert geometry["type"] == "Polygon"
    assert area == 2.0
