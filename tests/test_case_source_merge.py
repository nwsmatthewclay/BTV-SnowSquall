import pandas as pd

from scripts.merge_snow_squall_case_sources import attach_nws_text_records


def test_empty_nws_text_file_is_optional_evidence(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    records = [{
        "source_types": set(),
        "evidence_sources": set(),
        "source_records": 1,
    }]

    result, matched, added = attach_nws_text_records(records, path)

    assert result == records
    assert matched == 0
    assert added == 0
