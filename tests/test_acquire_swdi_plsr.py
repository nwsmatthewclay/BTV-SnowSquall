import pandas as pd

from scripts.acquire_swdi_plsr import _rest_year


class Response:
    status_code = 200
    text = "ztime,id,event,magnitude,city,county,state,source,lon,lat\n2014-01-02T12:00:00Z,1,SNOW SQUALL,-9999,Burlington,CHITTENDEN,VT,NWS,-73.2,44.5\n"

    def raise_for_status(self):
        return None


def test_rest_year_parses_squall_record(monkeypatch):
    def fake_get(url, timeout):
        assert 'plsr/' in url
        assert 'bbox=-80,40,-67,48' in url
        return Response()

    import scripts.acquire_swdi_plsr as mod
    monkeypatch.setattr(mod.requests, 'get', fake_get)
    frame = _rest_year(
        2014,
        pd.Timestamp('2014-01-01T00:00:00Z'),
        pd.Timestamp('2014-12-31T23:59:59Z'),
        'VT',
    )
    assert len(frame) == 1
    assert frame.iloc[0]['state'] == 'VT'
