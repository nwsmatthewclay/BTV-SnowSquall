"""Training weights and metrics that reduce storm/scan pseudo-replication."""
from __future__ import annotations
import numpy as np
import pandas as pd

def case_scan_balanced_weights(frame: pd.DataFrame, case_col="case_id", time_col="scan_time_utc"):
    """Give each case equal weight and each radar scan equal weight within a case.

    Multiple objects on one scan therefore cannot dominate a case, and a
    long-lived case cannot dominate the training set merely because it has
    more scans.
    """
    n=len(frame)
    if n==0: return np.zeros(0,dtype=float)
    if case_col in frame:
        cases=frame[case_col].astype(str).fillna("__missing_case__")
    else:
        cases=pd.Series("__all_cases__",index=frame.index)
    if time_col in frame:
        times=pd.to_datetime(frame[time_col],utc=True,errors="coerce").astype("int64")
        scan_key=times.where(times.ne(pd.Timestamp("NaT").value),pd.Series(np.arange(n),index=frame.index))
    else:
        scan_key=pd.Series(np.arange(n),index=frame.index)
    keys=pd.DataFrame({"case":cases.values,"scan":scan_key.values},index=frame.index)
    rows_per_scan=keys.groupby(["case","scan"],dropna=False)["case"].transform("size")
    scans_per_case=keys[["case","scan"]].drop_duplicates().groupby("case",dropna=False).size()
    weights=1.0/(rows_per_scan.to_numpy(dtype=float)*keys["case"].map(scans_per_case).to_numpy(dtype=float))
    weights*=len(scans_per_case)/weights.sum()
    return weights

def case_weighted_metrics(y,p,weights):
    from sklearn.metrics import average_precision_score,brier_score_loss,roc_auc_score
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float); w=np.asarray(weights,dtype=float)
    return {
        "roc_auc": float(roc_auc_score(y,p,sample_weight=w)) if len(np.unique(y))==2 else None,
        "pr_auc": float(average_precision_score(y,p,sample_weight=w)) if y.sum() else None,
        "brier": float(brier_score_loss(y,p,sample_weight=w)),
    }
