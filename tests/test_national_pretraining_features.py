import json

import joblib
import pandas as pd

from scripts.add_national_pretraining_features import augment


class FakeModel:
    def predict_proba(self, frame):
        n=len(frame)
        return [[0.8,0.2] for _ in range(n)]


def test_national_pretraining_feature_is_btv_safe_and_reproducible(tmp_path):
    root=tmp_path/'national_sqw_weak_model_15m'
    root.mkdir(parents=True)
    joblib.dump(FakeModel(),root/'weak_pretraining_model.joblib')
    (root/'metrics.json').write_text(json.dumps({
        'model_version':'national-test',
        'predictor_columns':['max_reflectivity_dbz','velocity_mean_kt'],
        'excluded_wfo':'BTV'
    }),encoding='utf-8')
    frame=pd.DataFrame({'max_reflectivity_dbz':[30.0],'velocity_mean_kt':[25.0]})
    augmented,summary=augment(frame,tmp_path)
    assert augmented.loc[0,'national_pretrain_probability_15m']==0.2
    assert summary['15m']['excluded_wfo']=='BTV'
    assert summary['30']['status'] == 'not_available'