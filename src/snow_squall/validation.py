"""Case-based validation utilities; never split adjacent scans randomly."""
from __future__ import annotations
import pandas as pd
from sklearn.model_selection import GroupKFold

def case_splits(df: pd.DataFrame, n_splits: int=5, group_col: str="case_id"):
    if group_col not in df.columns:
        raise ValueError(f"Missing validation group column: {group_col}")
    if df[group_col].isna().any():
        raise ValueError(f"Validation group column contains missing values: {group_col}")
    groups=df[group_col].astype(str)
    splitter=GroupKFold(n_splits=min(n_splits,groups.nunique()))
    return list(splitter.split(df,groups=groups))

def chronological_case_split(df: pd.DataFrame, fraction: float=0.2, time_col: str="scan_time"):
    if "case_id" not in df.columns or df["case_id"].isna().any():
        raise ValueError("Chronological case split requires non-missing case_id for every row.")
    if time_col not in df.columns:
        raise ValueError(f"Missing chronological split time column: {time_col}")
    cases=(df.groupby("case_id")[time_col].min().sort_values().index.tolist())
    cut=max(1,int(len(cases)*(1-fraction)))
    train_cases=set(cases[:cut])
    return df["case_id"].isin(train_cases), ~df["case_id"].isin(train_cases)
