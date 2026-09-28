"""Build a conservative null-object sampling manifest.

Null windows use a dedicated `window_id`. \`case_id\` is intentionally blank
for null samples so downstream case counts cannot confuse candidate-null windows
with historical verified cases.
"""
from __future__ import annotations

import argparse
import random
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
    radars: tuple[str, ...] = ("KCXX", "KTYX"),
):
    cases = pd.read_csv(cases_csv)
    starts = pd.to_datetime(cases["event_start_utc"], utc=True).dropna()

    excluded = [
        (
            start_time - pd.Timedelta(minutes=exclusion_before_minutes),
            start_time + pd.Timedelta(minutes=exclusion_after_minutes),
        )
        for start_time in starts
    ]

    times = pd.date_range(
        pd.Timestamp(start, tz="UTC"),
        pd.Timestamp(end, tz="UTC"),
        freq=f"{step_minutes}min",
    )

    candidates = [
        timestamp for timestamp in times
        if not any(left <= timestamp <= right for left, right in excluded)
    ]

    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected = sorted(candidates[:sample_count])

    rows = []
    for i, timestamp in enumerate(selected, start=1):
        null_id = f"NULL{i:04d}"
        for radar in radars:
            rows.append({
                "case_id": "",
                "window_id": f"{null_id}_{radar}",
                "radar_site": radar,
                "null_id": null_id,
                "window_center_utc": timestamp.isoformat().replace("+00:00", "Z"),
                "window_start_utc": (
                    timestamp - pd.Timedelta(minutes=90)
                ).isoformat().replace("+00:00", "Z"),
                "window_end_utc": (
                    timestamp + pd.Timedelta(minutes=90)
                ).isoformat().replace("+00:00", "Z"),
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
    parser.add_argument("--radars", nargs="+", default=["KCXX", "KTYX"])
    parser.add_argument("--output", default="data/manifests/banacos_null_windows.csv")
    args = parser.parse_args()

    result = build_null_windows(
        Path(args.cases),
        args.start,
        args.end,
        seed=args.seed,
        sample_count=args.sample_count,
        radars=tuple(args.radars),
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result)} candidate null radar windows to {args.output}")


if __name__ == "__main__":
    main()
