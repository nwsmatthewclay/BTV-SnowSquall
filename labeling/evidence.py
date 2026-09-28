"""Evidence-based snow-squall labeling with independent-source safeguards.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Evidence:
    source: str
    supports_positive: bool | None
    confidence: str
    note: str = ""

def combine_evidence(evidence: Iterable[Evidence]):
    items = list(evidence)
    if not items:
        return "uncertain", "low"

    positive = [e for e in items if e.supports_positive is True]
    negative = [e for e in items if e.supports_positive is False]

    if positive and not negative:
        sources = {e.source for e in positive if e.source}
        if len(sources) < 2:
            return "uncertain", "low"
        confidence = "high" if sum(e.confidence == "high" for e in positive) >= 2 else "medium"
        return "positive", confidence

    if negative and not positive:
        sources = {e.source for e in negative if e.source}
        if len(sources) < 2:
            return "uncertain", "low"
        confidence = "high" if sum(e.confidence == "high" for e in negative) >= 2 else "medium"
        return "negative", confidence

    return "uncertain", "low"
