import pandas as pd


def test_modern_training_separation_passes_without_overlap(tmp_path):
    from scripts.audit_modern_training_separation import audit
    modern=tmp_path/"modern.csv"
    dev=tmp_path/"dev.csv"
    pd.DataFrame([{"case_id":"MODERN_CASE1"}]).to_csv(modern,index=False)
    pd.DataFrame([{"case_id":"BTV20020101"}]).to_csv(dev,index=False)
    result=audit(modern,tmp_path)
    assert result["modern_case_count"]==1
    assert result["overlaps"]=={}
    assert result["training_eligible"] is False


def test_modern_training_separation_rejects_overlap(tmp_path):
    from scripts.audit_modern_training_separation import audit
    import pytest
    modern=tmp_path/"modern.csv"
    dev=tmp_path/"development.csv"
    pd.DataFrame([{"case_id":"BTV20191218"}]).to_csv(modern,index=False)
    pd.DataFrame([{"case_id":"BTV20191218"}]).to_csv(dev,index=False)
    with pytest.raises(ValueError,match="modern_development_overlap"):
        audit(modern,tmp_path)
