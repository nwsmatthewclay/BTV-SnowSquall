import json

import pandas as pd

from scripts.build_case_review_report import build


def test_case_review_report_renders(tmp_path):
    cases=tmp_path/'cases.csv'
    summary=tmp_path/'summary.json'
    output=tmp_path/'review.html'
    pd.DataFrame([
        {
            'candidate_id':'SSQ1',
            'episode_id':'EP1',
            'event_start_utc':'2026-01-01T12:00:00Z',
            'verification_class':'official_documented',
            'candidate_source':'NCEI_STORM_EVENTS',
            'narrative':'Snow squall reported.',
        }
    ]).to_csv(cases,index=False)
    summary.write_text(json.dumps({'unified_cases':1}),encoding='utf-8')
    build(cases,summary,output)
    text=output.read_text(encoding='utf-8')
    assert 'SSQ1' in text
    assert 'official_documented' in text
    assert 'Snow squall reported.' in text
