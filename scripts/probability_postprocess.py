"""Post-process multi-horizon research probabilities into a coherent cumulative sequence."""
from __future__ import annotations

import numpy as np


def monotone_cumulative_probabilities(probabilities: dict) -> dict:
    """Project available cumulative probabilities onto a nondecreasing sequence."""
    horizons = [15, 30, 45, 60]
    valid = []
    values = []
    for horizon in horizons:
        value = probabilities.get(str(horizon), probabilities.get(horizon))
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            valid.append(horizon)
            values.append(float(np.clip(value, 0.0, 1.0)))
    if not valid:
        return {}

    fitted = []
    starts = []
    ends = []
    means = []
    weights = []
    for i, value in enumerate(values):
        starts.append(i)
        ends.append(i)
        means.append(value)
        weights.append(1.0)
        while len(means) >= 2 and means[-2] > means[-1]:
            total_weight = weights[-2] + weights[-1]
            merged = (means[-2] * weights[-2] + means[-1] * weights[-1]) / total_weight
            means[-2] = merged
            weights[-2] = total_weight
            ends[-2] = ends[-1]
            means.pop()
            weights.pop()
            starts.pop()
            ends.pop()
    for start, end, mean in zip(starts, ends, means):
        fitted.extend([mean] * (end - start + 1))

    cumulative = {str(h): float(np.clip(v, 0.0, 1.0)) for h, v in zip(valid, fitted)}
    interval = {}
    previous = 0.0
    for h in horizons:
        key = str(h)
        if key in cumulative:
            current = cumulative[key]
            interval[key] = max(0.0, current - previous)
            previous = current
    return {"cumulative": cumulative, "interval": interval}
