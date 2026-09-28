from datetime import datetime,timezone
import pytest
from processing.environment import provider_for_time,canonicalize_environment_fields

def dt(text):
    return datetime.fromisoformat(text.replace("Z","+00:00"))

def test_environment_provider_boundaries_are_explicit():
    assert provider_for_time(dt("2007-03-31T23:59:00Z"))=="NARR"
    assert provider_for_time(dt("2007-04-01T00:00:00Z"))=="RUC"
    assert provider_for_time(dt("2012-04-30T23:59:00Z"))=="RUC"
    assert provider_for_time(dt("2012-05-01T00:00:00Z"))=="RAP"

def test_environment_units_are_canonicalized():
    fields=canonicalize_environment_fields("RAP",{"cape_jkg":100.0,"shear_0_6km_ms":10.0})
    assert fields["sbcape_jkg"]==100.0
    assert fields["shear_0_6km_kt"]==pytest.approx(19.43844,rel=1e-6)

def test_existing_canonical_field_wins_over_alias():
    fields=canonicalize_environment_fields("RAP",{"sbcape_jkg":250.0,"cape_jkg":100.0})
    assert fields["sbcape_jkg"]==250.0
