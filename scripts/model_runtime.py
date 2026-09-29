"""Safe runtime adapter for the research snow-squall probability model.

A model is never exposed to live products unless its metrics.json explicitly
marks the artifact as operationally released. Candidate models remain usable
for offline replay/diagnostics but return no live probability.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import joblib
import pandas as pd


class ModelRuntime:
    def __init__(self, model=None, feature_columns=None, metadata=None):
        self.model = model
        self.feature_columns = list(feature_columns or [])
        self.metadata = metadata or {}

    @property
    def horizon_minutes(self):
        target = str(self.metadata.get("target") or "")
        match = re.search(r"_(15|30|45|60)m$", target)
        return int(match.group(1)) if match else None

    @property
    def enabled(self) -> bool:
        return (
            self.model is not None
            and self.metadata.get("operational_release_status") == "released"
        )

    @classmethod
    def load(cls, model_dir: str | Path):
        root = Path(model_dir)
        metrics_path = root / "metrics.json"
        model_path = root / "baseline_model.joblib"
        if not metrics_path.exists() or not model_path.exists():
            return cls()

        metadata = json.loads(metrics_path.read_text(encoding="utf-8"))
        model = joblib.load(model_path)
        features = metadata.get("predictor_columns") or []
        return cls(model=model, feature_columns=features, metadata=metadata)

    def score(self, frame: pd.DataFrame):
        if not self.enabled:
            return None
        missing = [c for c in self.feature_columns if c not in frame.columns]
        if missing:
            raise ValueError(f"Live model feature columns missing: {missing}")
        return self.model.predict_proba(frame[self.feature_columns])[:, 1].tolist()
