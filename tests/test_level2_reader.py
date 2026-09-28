import sys
import types

from acquisition.level2_reader import read_level2


def test_level2_reader_falls_back_to_xradar(monkeypatch):
    fake_pyart = types.ModuleType("pyart")
    fake_pyart.io = types.SimpleNamespace(
        read_nexrad_archive=lambda path: (_ for _ in ()).throw(IndexError("msg_5"))
    )
    fake_tree = types.SimpleNamespace(
        pyart=types.SimpleNamespace(
            to_radar=lambda: types.SimpleNamespace(metadata={}, fields={"reflectivity"})
        )
    )
    fake_xradar = types.ModuleType("xradar")
    fake_xradar.io = types.SimpleNamespace(
        open_nexradlevel2_datatree=lambda path: fake_tree
    )

    monkeypatch.setitem(sys.modules, "pyart", fake_pyart)
    monkeypatch.setitem(sys.modules, "xradar", fake_xradar)

    radar = read_level2("bad-old-volume")
    assert radar.metadata["reader_backend"] == "xradar"


def test_level2_reader_reports_both_errors(monkeypatch):
    fake_pyart = types.ModuleType("pyart")
    fake_pyart.io = types.SimpleNamespace(
        read_nexrad_archive=lambda path: (_ for _ in ()).throw(IndexError("msg_5"))
    )
    fake_xradar = types.ModuleType("xradar")
    fake_xradar.io = types.SimpleNamespace(
        open_nexradlevel2_datatree=lambda path: (_ for _ in ()).throw(ValueError("bad header"))
    )

    monkeypatch.setitem(sys.modules, "pyart", fake_pyart)
    monkeypatch.setitem(sys.modules, "xradar", fake_xradar)

    try:
        read_level2("bad-volume")
    except RuntimeError as exc:
        message = str(exc)
        assert "Py-ART IndexError" in message
        assert "xradar ValueError" in message
    else:
        raise AssertionError("Expected dual-reader RuntimeError")
