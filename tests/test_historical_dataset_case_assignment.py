import inspect
from scripts.build_historical_dataset import enrich


def test_temporal_case_inference_is_opt_in():
    params = inspect.signature(enrich).parameters
    assert params['allow_temporal_case_inference'].default is False
