import numpy as np
import numpy.ma as ma

from processing.radar_grid import lowest_valid_sweep


class _SweepIndex:
    def __init__(self, values):
        self.data = np.asarray(values, dtype=int)


class _FakeRadar:
    def __init__(self, field_data):
        self.fields = {"velocity": {"data": field_data}}
        self.sweep_start_ray_index = _SweepIndex([0, 2, 4])
        self.sweep_end_ray_index = _SweepIndex([1, 3, 5])


def test_lowest_valid_sweep_skips_masked_sweep():
    data = ma.masked_all((6, 4), dtype=float)
    data[2:4] = 1.0
    data[4:6] = 2.0
    radar = _FakeRadar(data)

    assert lowest_valid_sweep(radar, "velocity") == 1


def test_lowest_valid_sweep_returns_none_for_missing_field():
    radar = _FakeRadar(np.ones((6, 4), dtype=float))
    assert lowest_valid_sweep(radar, "reflectivity") is None
