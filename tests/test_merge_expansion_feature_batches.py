import pandas as pd

from scripts.merge_expansion_feature_batches import merge


def test_merge_expansion_batches_deduplicates(tmp_path):
    current=tmp_path/'current.csv'
    prior=tmp_path/'prior.csv'
    output=tmp_path/'out.csv'
    rows=[
        {'row_identity_key':'a','scan_time_utc':'2026-01-01T12:00:00Z','x':1},
        {'row_identity_key':'b','scan_time_utc':'2026-01-01T12:05:00Z','x':2},
    ]
    pd.DataFrame(rows).to_csv(prior,index=False)
    pd.DataFrame([
        {'row_identity_key':'b','scan_time_utc':'2026-01-01T12:05:00Z','x':20},
        {'row_identity_key':'c','scan_time_utc':'2026-01-01T12:10:00Z','x':3},
    ]).to_csv(current,index=False)
    merge(current,prior,output)
    d=pd.read_csv(output)
    assert list(d['row_identity_key']) == ['a','b','c']
    assert float(d.loc[d.row_identity_key.eq('b'),'x'].iloc[0]) == 20.0
