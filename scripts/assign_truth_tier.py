"""Assign reproducible evidence tiers to snow-squall case records.

Tiers are descriptive evidence metadata, not a claim that the event is ground truth.
They are used to keep high-confidence and weakly supervised populations separate.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

TIER_MAP = {
    "official_study_warning_verified": ("A+", 1.00),
    "study_warning_verified": ("A+", 1.00),
    "official_plus_study": ("A+", 1.00),
    "study_verified": ("A", 1.00),
    "official_plus_independent_report": ("A-", 0.90),
    "official_plus_warning_and_report": ("A-", 0.90),
    "official_plus_warning": ("B+", 0.85),
    "warning_verified": ("B+", 0.85),
    "official_documented": ("B", 0.70),
    "warning_plus_report": ("C+", 0.55),
    "warning_only": ("C", 0.45),
    "unverified_report_only": ("D", 0.25),
    "official_screening_candidate": ("D", 0.20),
}

def assign(frame: pd.DataFrame) -> pd.DataFrame:
    d = frame.copy()
    source = d.get("verification_class", pd.Series("", index=d.index)).fillna("").astype(str)
    d["truth_tier"] = source.map(lambda x: TIER_MAP.get(x, ("D", 0.10))[0])
    d["evidence_weight"] = source.map(lambda x: TIER_MAP.get(x, ("D", 0.10))[1])
    d["truth_tier_policy"] = "descriptive_evidence_tier_v1"
    return d

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    d = assign(pd.read_csv(a.input))
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(a.output, index=False)
    print(d["truth_tier"].value_counts(dropna=False).sort_index().to_string())
    print(d.groupby("truth_tier")["evidence_weight"].first().sort_index().to_string())

if __name__ == "__main__":
    main()
