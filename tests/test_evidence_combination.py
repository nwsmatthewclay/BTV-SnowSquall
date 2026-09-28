from labeling.evidence import Evidence, combine_evidence

def test_single_positive_source_is_not_final_positive():
    result=combine_evidence([Evidence('radar',True,'high')])
    assert result==('uncertain','low')

def test_two_independent_positive_sources_can_support_positive_label():
    result=combine_evidence([Evidence('radar',True,'high'),Evidence('surface',True,'medium')])
    assert result==('positive','medium')

def test_duplicate_same_source_does_not_count_as_independent_evidence():
    result=combine_evidence([Evidence('radar',True,'high'),Evidence('radar',True,'high')])
    assert result==('uncertain','low')

def test_conflicting_sources_remain_uncertain():
    result=combine_evidence([Evidence('radar',True,'high'),Evidence('surface',False,'high')])
    assert result==('uncertain','low')