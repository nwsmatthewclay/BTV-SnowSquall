"""Train and compare interpretable baseline classifiers."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from snow_squall.features import add_derived_features, select_features
from snow_squall.validation import chronological_case_split
from snow_squall.metrics import probabilistic_metrics

@dataclass
class ModelResult:
    name: str
    model: object
    metrics: dict

def train_baselines(frame: pd.DataFrame):
    frame = add_derived_features(frame.copy())
    if "snow_squall_30min" not in frame:
        raise ValueError("snow_squall_30min target is required")
    features = select_features(frame)
    train, test = chronological_case_split(frame)
    X_train, y_train = train[features], train["snow_squall_30min"]
    X_test, y_test = test[features], test["snow_squall_30min"]
    candidates = {
        "logistic": make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
            LogisticRegression(max_iter=2000, class_weight="balanced")),
        "random_forest": make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
            RandomForestClassifier(n_estimators=400, min_samples_leaf=4,
                class_weight="balanced_subsample", random_state=42, n_jobs=-1)),
        "hist_gradient_boosting": make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
            HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                max_leaf_nodes=15, random_state=42)),
    }
    results = []
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        probability = model.predict_proba(X_test)[:, 1]
        results.append(ModelResult(name, model, probabilistic_metrics(y_test, probability)))
    return results
