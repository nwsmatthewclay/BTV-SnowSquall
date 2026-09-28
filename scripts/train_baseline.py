"""Train a first interpretable 30-minute snow-squall probability baseline."""
from pathlib import Path
import sys
import pandas as pd
from sklearn.metrics import brier_score_loss

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from snow_squall.features import add_derived_features, select_features
from snow_squall.model import build_logistic_baseline
from snow_squall.labels import exclude_leakage_columns
from snow_squall.validation import chronological_case_split

DATA=ROOT/"data/training/training_table.csv"
MODEL=ROOT/"models/snow_squall_logistic_v0.joblib"

def main():
    if not DATA.exists():
        raise SystemExit("Training table does not exist. Initialize/populate it first.")
    df=pd.read_csv(DATA)
    if "snow_squall_30min" not in df:
        raise SystemExit("Training table needs a snow_squall_30min target.")
    df=add_derived_features(df)
    feature_cols=[c for c in select_features(df,include_optional=True) if c in exclude_leakage_columns(df.columns)]
    train_mask,test_mask=chronological_case_split(df)
    train=df.loc[train_mask].dropna(subset=["snow_squall_30min"])
    test=df.loc[test_mask].dropna(subset=["snow_squall_30min"])
    if train.empty or test.empty:
        raise SystemExit("Need populated training and test cases before fitting.")
    model=build_logistic_baseline(feature_cols)
    model.pipeline.fit(train[feature_cols],train["snow_squall_30min"])
    prob=model.predict_proba(test)
    print("features:",len(feature_cols))
    print("train rows:",len(train),"test rows:",len(test))
    print("Brier score:",brier_score_loss(test["snow_squall_30min"],prob))
    MODEL.parent.mkdir(parents=True,exist_ok=True)
    model.save(str(MODEL))

if __name__=="__main__":
    main()
