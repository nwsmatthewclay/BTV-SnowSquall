import pandas as pd
import pytest
from scripts.audit_radar_reconstruction import audit

def test_gate_counts_successful_zero_object_volumes(tmp_path):
    root=tmp_path/"input"; root.mkdir()
    for name in ("a","b","c"): (root/name).write_bytes(b"x")
    obj=tmp_path/"objects.csv"; err=tmp_path/"errors.csv"
    pd.DataFrame([{"source_file":str(root/"a"),"reader_backend":"pyart"}]).to_csv(obj,index=False)
    pd.DataFrame(columns=["source_file","error_type"]).to_csv(err,index=False)
    s=audit(obj,err,root,max_failure_rate=0.20)
    assert s["expected_input_volumes"]==3
    assert s["successful_input_volumes"]==3
    assert s["successful_zero_object_volumes"]==2

def test_gate_blocks_material_failure_rate(tmp_path):
    root=tmp_path/"input"; root.mkdir()
    paths=[]
    for name in ("a","b","c","d","e"):
        p=root/name; p.write_bytes(b"x"); paths.append(str(p))
    obj=tmp_path/"objects.csv"; err=tmp_path/"errors.csv"
    pd.DataFrame([{"source_file":paths[0],"reader_backend":"pyart"}]).to_csv(obj,index=False)
    pd.DataFrame([{"source_file":p,"error_type":"reader"} for p in paths[1:]]).to_csv(err,index=False)
    with pytest.raises(ValueError,match="failure rate"):
        audit(obj,err,root,max_failure_rate=0.20)
