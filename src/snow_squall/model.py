"""Baseline probabilistic snow-squall models."""
from __future__ import annotations
from dataclasses import dataclass
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

@dataclass
class SnowSquallModel:
    pipeline: Pipeline
    feature_columns: list[str]

    def predict_proba(self, frame: pd.DataFrame):
        return self.pipeline.predict_proba(frame[self.feature_columns])[:,1]

    def save(self, path: str):
        joblib.dump(self, path)

    @staticmethod
    def load(path: str):
        return joblib.load(path)

def build_logistic_baseline(feature_columns: list[str]) -> SnowSquallModel:
    numeric=Pipeline([
        ("imputer",SimpleImputer(strategy="median",add_indicator=True)),
        ("scale",StandardScaler()),
    ])
    pre=ColumnTransformer([("numeric",numeric,feature_columns)],remainder="drop")
    pipe=Pipeline([
        ("preprocess",pre),
        ("model",LogisticRegression(max_iter=2000,class_weight="balanced")),
    ])
    return SnowSquallModel(pipe,feature_columns)
