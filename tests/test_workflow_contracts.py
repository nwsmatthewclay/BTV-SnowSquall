from pathlib import Path

import yaml


WORKFLOWS = [
    '.github/workflows/snow-squall-case-discovery.yml',
    '.github/workflows/snow-squall-iem-lsr-harvest.yml',
    '.github/workflows/snow-squall-nws-text-review.yml',
    '.github/workflows/snow-squall-case-ledger.yml',
    '.github/workflows/snow-squall-expansion-dataset.yml',
    '.github/workflows/snow-squall-expansion-controller.yml',
    '.github/workflows/snow-squall-candidate-model-refresh.yml',
    '.github/workflows/snow-squall-research-operational-candidate.yml',
    '.github/workflows/snow-squall-operational-release-review.yml',
    '.github/workflows/national-sqw-radar-sample-controller.yml',
    '.github/workflows/snow-squall-live-shadow.yml',
    '.github/workflows/national-sqw-radar-pretraining.yml',
    '.github/workflows/snow-squall-modern-validation.yml',
    '.github/workflows/snow-squall-archived-replay-smoke.yml',
]


def test_snow_squall_workflows_parse_and_have_required_keys():
    for name in WORKFLOWS:
        path=Path(name)
        assert path.exists(), name
        data=yaml.safe_load(path.read_text(encoding='utf-8'))
        assert isinstance(data, dict), name
        assert 'jobs' in data and data['jobs'], name
        assert any(key in data for key in ('on', True)), name
        for job_name, job in data['jobs'].items():
            assert 'runs-on' in job, f'{name}:{job_name}'
            assert 'steps' in job and job['steps'], f'{name}:{job_name}'


def test_expansion_workflow_has_supervised_training_gate():
    path=Path('.github/workflows/snow-squall-expansion-dataset.yml')
    text=path.read_text(encoding='utf-8')
    assert 'Freeze supervised positive training cohort' in text
    assert 'training_eligible' in text
    assert 'snow_squall_training_cases.csv' in text
    assert 'snow_squall_training_objects.csv' in text
    assert 'snow_squall_training_labeled.csv' in text
    assert 'snow_squall_training_cases.csv' in text
    assert 'audit_expansion_dataset.py' in text
    assert 'audit_live_model_compatibility.py' in text


def test_replay_and_shadow_contracts_keep_candidate_scoring_research_only():
    replay = Path('scripts/historical_operational_replay.py').read_text(encoding='utf-8')
    process = Path('scripts/process_live_volume.py').read_text(encoding='utf-8')
    parity = Path('scripts/audit_live_feature_parity.py').read_text(encoding='utf-8')
    shadow = Path('.github/workflows/snow-squall-live-shadow.yml').read_text(encoding='utf-8')
    assert 'research_replay=(model_dir is not None)' in replay
    assert 'score_candidate' in process
    assert 'candidate_blocked' in process
    assert 'def audit_track' in parity
    assert 'ref: snow-squall-model-foundation' in shadow


def test_archived_replay_workflow_has_four_horizon_qc():
    text = Path('.github/workflows/snow-squall-archived-replay-smoke.yml').read_text(encoding='utf-8')
    assert 'historical_operational_replay.py' in text
    assert 'audit_candidate_replay.py' in text
    assert 'audit_live_feature_parity.py' in text
    assert 'for horizon in (15, 30, 45, 60)' in text or 'for h in (15, 30, 45, 60)' in text or all(x in text for x in ('15', '30', '45', '60'))
    assert 'BTV20181121' in text


def test_archived_replay_builds_unified_score_timeline():
    text = Path('.github/workflows/snow-squall-archived-replay-smoke.yml').read_text(encoding='utf-8')
    assert 'merge_replay_horizon_scores.py' in text
    assert 'score_timeline.json' in text


def test_historical_benchmark_replay_workflow_contract():
    text = Path('.github/workflows/historical_benchmark_replay.yml').read_text(encoding='utf-8')
    assert 'historical_download.py' in text
    assert 'reconstruct_pilot.py' in text
    assert 'SQCL-2002-03-23-KBTV' in text
    assert 'KCXX KTYX' in text


def test_candidate_refresh_has_legacy_bootstrap_without_yaml_newline_break():
    text = Path('.github/workflows/snow-squall-candidate-model-refresh.yml').read_text(encoding='utf-8')
    assert 'continue-on-error: true' in text
    assert 'Bootstrap candidate from prior successful expansion model' in text
    assert "candidate_mode: bootstrap_legacy_feature_contract" in text
    assert "printf '%s\\n'" in text
    assert "printf '%s\n'" not in text


def test_research_operational_candidate_gate_keeps_probability_disabled():
    text = Path('.github/workflows/snow-squall-research-operational-candidate.yml').read_text(encoding='utf-8')
    assert 'audit_research_operational_candidate.py' in text
    assert 'snow-squall-research-operational-candidate' in text
    audit = Path('scripts/audit_research_operational_candidate.py').read_text(encoding='utf-8')
    assert '"probability_enablement": False' in audit
    assert 'candidate_mode' in audit
