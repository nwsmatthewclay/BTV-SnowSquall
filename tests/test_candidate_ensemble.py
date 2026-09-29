import numpy as np

from scripts.train_candidate_ensemble import class_balanced_weights, estimator


def test_class_balanced_weights_equalizes_class_totals():
    weights = class_balanced_weights(np.array([0, 0, 0, 1], dtype=int))
    assert np.isclose(weights[0], 2.0 / 3.0)
    assert np.isclose(weights[3], 2.0)
    assert np.isclose(weights[:3].sum(), weights[3])


def test_candidate_ensemble_estimator_has_three_fixed_members():
    model = estimator()
    assert model.named_steps['model'].voting == 'soft'
    assert [name for name, _ in model.named_steps['model'].estimators] == ['hgb', 'rf', 'extra']
