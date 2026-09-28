"""Build a conservative null-object sampling manifest.

The manifest selects winter background windows outside a configurable exclusion
buffer around verified Banacos events. It is intended to feed the same radar
reconstruction pipeline as positive cases, producing genuine non-event object
samples rather than treating pre-event objects as negatives.
"""
from __future__ import annotations

import argparse
import random
from datetime import timedelta
from pathlib import Path

import pandas as pd


def build_null_windows(
    cases_csv: Path,
    start: str,
    end: str,
    step_minutes: int = 180,
    exclusion_before_minutes: int = 180,
    exclusion_after_minutes: int = 180,
    seed: int = 42,
    sample_count: int = 100,
):
    cases = pd.read_csv(cases_csv)
    starts = pd.to_datetime(cases["event_start_utc"], utc=True).dropna()

    excluded = []
    for start_time in starts:
        excluded.append((
            start_time - pd.Timedelta(minutes=exclusion_before_minutes),
            start_time + pd.Timedelta(minutes=exclusion_after_minutes),
        ))

    times = pd.date_range(
        pd.Timestamp(start, tz="UTC"),
        pd.Timestamp(end, tz="UTC"),
        freq=f"{step_minutes}min",
    )

    candidates = []
    for timestamp in times:
        if any(left <= timestamp <= right for left, right in excluded):
            continue
        candidates.append(timestamp)

    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected = sorted(candidates[:sample_count])

    rows = []
    for i, timestamp in enumerate(selected, start=1):
        rows.append({
            "null_id": f"NULL{i:04d}",
            "window_center_utc": timestamp.isoformat().replace("+00:00", "Z"),
            "window_start_utc": (timestamp - pd.Timedelta(minutes=90)).isoformat().replace("+00:00", "Z"),
            "window_end_utc": (timestamp + pd.Timedelta(minutes=90)).isoformat().replace("+00:00", "Z"),
            "source": "banacos_winter_background",
            "label_status": "candidate_null",
            "selection_seed": seed,
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="data/manifests/banacos_2014_cases.csv")
    parser.add_argument("--start", default="2005-11-01T00:00:00Z")
    parser.add_argument("--end", default="2006-03-31T21:00:00Z")
    parser.add_argument("--sample-count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="data/manifests/banacos_null_windows.csv")
    args = parser.parse_args()

    result = build_null_windows(
        Path(args.cases),
        args.start,
        args.end,
        seed=args.seed,
        sample_count=args.sample_count,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result)} candidate null windows to {args.output}")


if __name__ == "__main__":
    main()
