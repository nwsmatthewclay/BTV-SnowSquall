from pathlib import Path

import yaml


WORKFLOWS = [
    '.github/workflows/snow-squall-case-discovery.yml',
    '.github/workflows/snow-squall-iem-lsr-harvest.yml',
    '.github/workflows/snow-squall-nws-text-review.yml',
    '.github/workflows/snow-squall-case-ledger.yml',
    '.github/workflows/snow-squall-expansion-dataset.yml',
    '.github/workflows/snow-squall-expansion-controller.yml',
    '.github/workflows/national-sqw-radar-pretraining.yml',
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
