"""Stateful storm-object probability updates."""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
import numpy as np

@dataclass
class ObjectProbabilityState:
    track_id: int
    history: deque
    probability: float | None = None

    @classmethod
    def create(cls, track_id, max_history=12):
        return cls(track_id=track_id, history=deque(maxlen=max_history))

    def update(self, timestamp, probability, max_probability_step=0.35):
        probability = float(np.clip(probability, 0.0, 1.0))
        if self.probability is not None:
            probability = float(np.clip(
                probability,
                self.probability - max_probability_step,
                self.probability + max_probability_step,
            ))
        self.probability = probability
        self.history.append({"scan_time": timestamp, "probability": probability})
        return probability

    def trend(self, scans=3):
        if len(self.history) < 2:
            return 0.0
        values = [x["probability"] for x in list(self.history)[-scans:]]
        return float(values[-1] - values[0])
