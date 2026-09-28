import pandas as pd
from scripts.audit_feature_coverage import audit

def test_zero_coverage_is_classified_by_availability_policy(tmp_path):
    data=tmp_path/'data.csv'; schema=tmp_path/'schema.csv'
    pd.DataFrame([{'scan_time_utc':'2010-01-01T12:00Z','object_id':1,'radar_site':'KCXX','reflectivity_max_dbz':35.0}]).to_csv(data,index=False)
    pd.DataFrame([
      {'field':'reflectivity_max_dbz','group':'reflectivity','type':'float','description':'x','required':'true','availability_policy':'radar_available'},
      {'field':'mrms_reflectivity_dbz','group':'mrms','type':'float','description':'x','required':'true','availability_policy':'modern_2014_plus'},
    ]).to_csv(schema,index=False)
    result=audit(data,schema)
    assert 'mrms_reflectivity_dbz' in result['zero_coverage_expected']
    assert 'reflectivity_max_dbz' not in result['zero_coverage_unexpected']