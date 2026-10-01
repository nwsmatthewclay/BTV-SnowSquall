import numpy as np
import pandas as pd
from src.snow_squall.analog_candidate_runtime import AnalogCandidateRuntime

def test_candidate_runtime_enriches_and_scores(tmp_path):
    from src.snow_squall.analogs import AnalogLibrary
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    d=pd.DataFrame({
      "case_id":["A","B"],"scan_time_utc":["2026-01-01T00:00:00Z","2026-01-02T00:00:00Z"],
      "max_reflectivity_dbz":[20.,25.],"snsq":[.5,1.],
      "squall_onset_within_15m":[0,1],"squall_onset_within_30m":[0,1],
      "squall_onset_within_45m":[0,1],"squall_onset_within_60m":[0,1],
    })
    lib=AnalogLibrary.fit(d)
    model=Pipeline([("impute",SimpleImputer(strategy="median")),("model",LogisticRegression())])
    x=lib.query(d.iloc[[1]],top_k=1)
    train=d.iloc[[0]].assign(analog_onset_rate_15m=x["analog_onset_rate_15m"].to_numpy())
    y=np.array([0])
    # Use a tiny two-row fitting frame for valid binary training.
    train2=d.copy()
    an=lib.query(d,top_k=1)
    train2["analog_onset_rate_15m"]=an["analog_onset_rate_15m"].fillna(0)
    model=Pipeline([("impute",SimpleImputer(strategy="median")),("model",LogisticRegression())])
    model.fit(train2[["max_reflectivity_dbz","analog_onset_rate_15m"]],[0,1])
    runtime=AnalogCandidateRuntime({"target":"squall_onset_within_15m","models":{"logistic":{"model":model,"predictors":["max_reflectivity_dbz","analog_onset_rate_15m"]}},"analog_library":lib})
    out=runtime.score(pd.DataFrame([{"timestamp":"2026-01-03T00:00:00Z","max_reflectivity_dbz":24.}]))
    assert "logistic" in out and len(out["logistic"])==1
