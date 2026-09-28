import json
from scripts.summarize_baseline_horizons import summarize

def test_horizon_summary_compares_models_to_climatology(tmp_path):
    root = tmp_path
    for horizon, brier, clim in [(15, 0.01, 0.02), (30, 0.02, 0.03)]:
        d = root / f'baseline_model_{horizon}m'
        d.mkdir()
        (d / 'metrics.json').write_text(json.dumps({
            'evaluation_status': 'case_held_out_exploratory',
            'training_rows': 100,
            'training_groups': 9,
            'positive_case_group_count': 5,
            'metrics': {
                'positive_rows': 5,
                'negative_rows': 95,
                'auc_roc': 0.8,
                'average_precision': 0.4,
                'brier_score': brier,
                'climatology': {'brier_score': clim},
            },
        }), encoding='utf-8')
    report = summarize(root)
    assert [x['horizon_minutes'] for x in report['horizons']] == [15, 30]
    assert report['horizons'][0]['brier_skill_vs_climatology'] == 0.5