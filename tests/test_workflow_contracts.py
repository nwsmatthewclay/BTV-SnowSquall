    assert 'reconstruct_pilot.py' in text
    assert 'SQCL-2002-03-23-KBTV' in text
    assert 'KCXX KTYX' in text


def test_candidate_refresh_has_legacy_bootstrap_without_yaml_newline_break():
    text = Path('.github/workflows/snow-squall-candidate-model-refresh.yml').read_text(encoding='utf-8')
    assert 'continue-on-error: true' in text
    assert 'Establish candidate training mode' in text
    assert "candidate_mode" in text
    assert "limited_data_bootstrap" in text
    assert "printf '%s\\n'" in text
    assert "printf '%s\n'" not in text


def test_research_operational_candidate_gate_keeps_probability_disabled():
    text = Path('.github/workflows/snow-squall-research-operational-candidate.yml').read_text(encoding='utf-8')
    assert 'audit_research_operational_candidate.py' in text
    assert 'snow-squall-research-operational-candidate' in text
    audit = Path('scripts/audit_research_operational_candidate.py').read_text(encoding='utf-8')
    assert '"probability_enablement": False' in audit
    assert 'candidate_mode' in audit