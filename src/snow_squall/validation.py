"""Case-based validation utilities; never split adjacent scans randomly."""
from __future__ import annotations
import pandas as pd
from sklearn.model_selection import GroupKFold

def case_splits(df: pd.DataFrame, n_splits: int=5, group_col: str="case_id"):
    groups=df[group_col].astype(str)
    splitter=GroupKFold(n_splits=min(n_splits,groups.nunique()))
    return list(splitter.split(df,groups=groups))

def chronological_case_split(df: pd.DataFrame, fraction: float=0.2, time_col: str="scan_time"):
    cases=(df.groupby("case_id")[time_col].min().sort_values().index.tolist())
    cut=max(1,int(len(cases)*(1-fraction)))
    train_cases=set(cases[:cut])
    return df["case_id"].isin(train_cases), ~df["case_id"].isin(train_cases)
