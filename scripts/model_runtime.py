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
import numpy as np
import pandas as pd


class ModelRuntime:
    def __init__(self, model=None, feature_columns=None, metadata=None, calibrator=None):
        self.model = model
        self.feature_columns = list(feature_columns or [])
        self.metadata = metadata or {}
        self.calibrator = calibrator

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
        calibrator_path = root / "probability_calibrator.joblib"
        calibrator = joblib.load(calibrator_path) if calibrator_path.exists() else None
        return cls(model=model, feature_columns=features, metadata=metadata, calibrator=calibrator)

    def score_candidate(self, frame: pd.DataFrame):
        """Score an explicitly research-only candidate bundle for replay or shadow use."""
        if self.model is None:
            return None
        working = frame.copy()
        for column in self.feature_columns:
            if column not in working.columns:
                working[column] = float('nan')
        probabilities = self.model.predict_proba(working[self.feature_columns])[:, 1]
        if self.calibrator is not None:
            eps = 1e-6
            clipped = np.clip(probabilities, eps, 1.0 - eps)
            logits = np.log(clipped / (1.0 - clipped))
            probabilities = self.calibrator.predict_proba(logits.reshape(-1, 1))[:, 1]
        return probabilities.tolist()
    def score(self, frame: pd.DataFrame):
        if not self.enabled:
            return None
        missing = [c for c in self.feature_columns if c not in frame.columns]
        if missing:
            raise ValueError(f"Live model feature columns missing: {missing}")
        return self.model.predict_proba(frame[self.feature_columns])[:, 1].tolist()
