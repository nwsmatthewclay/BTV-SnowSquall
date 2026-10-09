from pathlib import Path


def test_radar_png_renderers_disable_equal_aspect_letterboxing():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "build_live_radar_mosaic.py").read_text(encoding="utf-8")
    # Every image exported to Leaflet ImageOverlay must occupy the complete
    # PNG canvas or the browser stretches transparent letterbox margins over
    # the geographic bounds and displaces the apparent radar echo locations.
    assert source.count('ax.set_aspect("auto")') >= 4
    assert 'write_cursor_grid(args.output_image.parent, mosaic, site_velocity_fields, latlon=grid_latlon)' in source


def test_cursor_readout_prefers_actual_grid_coordinate_axes():
    root = Path(__file__).resolve().parents[1]
    js = (root / "viewer" / "live.js").read_text(encoding="utf-8")
    assert "function nearestAxisIndex(axis,value)" in js
    assert "cursorGrid.latitude_axis" in js
    assert "cursorGrid.longitude_axis" in js
    assert "row=nearestAxisIndex(latAxis,Number(lat))" in js
    assert "col=nearestAxisIndex(lonAxis,Number(lon))" in js
