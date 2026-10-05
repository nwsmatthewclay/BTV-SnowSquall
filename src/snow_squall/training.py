"""Training weights and metrics that reduce storm/scan pseudo-replication."""
from __future__ import annotations
import numpy as np
import pandas as pd

def case_scan_balanced_weights(
    frame: pd.DataFrame,
    case_col="case_id",
    time_col="scan_time_utc",
    group_col="split_group",
):
    """Give each independent training group equal total weight and each scan equal weight within that group.

    ``split_group`` is preferred when present because the training population
    contains both positive cases/episodes and null windows. Falling back to
    ``case_id`` alone would put every null row with a missing case ID into one
    giant pseudo-case and distort the case/scan balancing as the null dataset
    grows.
    """
    n = len(frame)
    if n == 0:
        return np.zeros(0, dtype=float)

    if group_col in frame and frame[group_col].notna().any():
        groups = frame[group_col].astype("string")
    else:
        # Backward-compatible fallback for callers that do not materialize the
        # common split-group key first. Prefer physical episodes, then cases,
        # then null windows, and make missing IDs explicit and row-unique.
        groups = pd.Series(pd.NA, index=frame.index, dtype="string")
        if "episode_id" in frame:
            episode = frame["episode_id"].astype("string")
            groups = groups.fillna(episode.where(episode.notna() & episode.ne(""), pd.NA).map(lambda x: f"episode:{x}" if pd.notna(x) else pd.NA))
        if case_col in frame:
            case = frame[case_col].astype("string")
            groups = groups.fillna(case.where(case.notna() & case.ne(""), pd.NA).map(lambda x: f"case:{x}" if pd.notna(x) else pd.NA))
        if "null_id" in frame:
            nulls = frame["null_id"].astype("string")
            groups = groups.fillna(nulls.where(nulls.notna() & nulls.ne(""), pd.NA).map(lambda x: f"null:{x}" if pd.notna(x) else pd.NA))
        groups = groups.fillna(pd.Series([f"row:{i}" for i in range(n)], index=frame.index))

    if time_col in frame:
        times = pd.to_datetime(frame[time_col], utc=True, errors="coerce")
        scan_key = times.astype("int64")
        invalid = times.isna()
        if invalid.any():
            scan_key = scan_key.astype("object")
            scan_key.loc[invalid] = [f"row:{i}" for i in frame.index[invalid]]
    else:
        scan_key = pd.Series([f"row:{i}" for i in range(n)], index=frame.index)

    keys = pd.DataFrame({"group": groups.astype(str).values, "scan": scan_key.values}, index=frame.index)
    rows_per_scan = keys.groupby(["group", "scan"], dropna=False)["group"].transform("size")
    scans_per_group = keys[["group", "scan"]].drop_duplicates().groupby("group", dropna=False).size()
    weights = 1.0 / (
        rows_per_scan.to_numpy(dtype=float)
        * keys["group"].map(scans_per_group).to_numpy(dtype=float)
    )
    total_groups = max(len(scans_per_group), 1)
    weights *= total_groups / weights.sum()
    return weights

def case_weighted_metrics(y,p,weights):
    from sklearn.metrics import average_precision_score,brier_score_loss,roc_auc_score
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float); w=np.asarray(weights,dtype=float)
    return {
        "roc_auc": float(roc_auc_score(y,p,sample_weight=w)) if len(np.unique(y))==2 else None,
        "pr_auc": float(average_precision_score(y,p,sample_weight=w)) if y.sum() else None,
        "brier": float(brier_score_loss(y,p,sample_weight=w)),
    }
