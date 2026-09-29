import json
import pandas as pd


def test_validation_viewer_catalog_is_non_scoring(tmp_path):
    from scripts.build_modern_validation_viewer_catalog import build
    src=tmp_path/"summary.csv"
    pd.DataFrame([{"case_id":"CASE1","radar_site":"KCXX","minimum_visibility_mi":0.12}]).to_csv(src,index=False)
    out=tmp_path/"viewer/data/validation/catalog.json"
    payload=build(src,out)
    assert payload["scoring_status"]=="not_scored"
    assert payload["training_eligible"] is False
    assert payload["cases"][0]["case_id"]=="CASE1"
    assert out.exists()
