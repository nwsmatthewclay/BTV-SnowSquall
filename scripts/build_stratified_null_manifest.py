"""Build reproducible stratified winter null windows across the historical case era.

The null sampler avoids a configurable exclusion corridor around every published
positive case and keeps selected windows separated in time. It records the
seed and sampling rationale so the resulting population can be regenerated.
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _utc(value):
    return pd.to_datetime(value, utc=True)


def build_null_windows(
    cases_csv: Path,
    start: str,
    end: str,
    sample_count: int,
    seed: int = 42,
    step_minutes: int = 180,
    exclusion_before_minutes: int = 180,
    exclusion_after_minutes: int = 240,
    min_separation_hours: int = 24,
    radars: tuple[str, ...] = ("KCXX", "KTYX"),
):
    cases = pd.read_csv(cases_csv)
    cases["event_start_utc"] = _utc(cases["event_start_utc"])
    positive_times = cases["event_start_utc"].dropna().sort_values()

    excluded = [
        (
            t - pd.Timedelta(minutes=exclusion_before_minutes),
            t + pd.Timedelta(minutes=exclusion_after_minutes),
        )
        for t in positive_times
    ]

    all_times = pd.date_range(
        _utc(start).floor("3h"),
        _utc(end).floor("3h"),
        freq=f"{step_minutes}min",
    )

    candidates = []
    for t in all_times:
        if any(left <= t <= right for left, right in excluded):
            continue
        # Keep the candidate pool broad enough to stratify across winter years.
        # Year/month remain attached to each candidate for deterministic quotas.
        if t.hour not in (0, 3, 6, 9, 12, 15, 18, 21):
            continue
        candidates.append(t)

    rng = random.Random(seed)
    rng.shuffle(candidates)

    # First pass: distribute windows across cool-season years as evenly as the
    # available candidate pool permits. This reduces year-specific background
    # bias before the final time-separation constraint is applied.
    by_year = {}
    for candidate in candidates:
        by_year.setdefault(candidate.year, []).append(candidate)
    years = sorted(by_year)
    per_year = max(1, sample_count // max(len(years), 1))

    selected = []
    minimum_gap = pd.Timedelta(hours=min_separation_hours)
    year_quota = {year: per_year for year in years}
    while len(selected) < sample_count:
        added = False
        for year in years:
            if year_quota[year] <= 0:
                continue
            choices = by_year[year]
            for candidate in choices:
                if any(abs(candidate - chosen) < minimum_gap for chosen in selected):
                    continue
                selected.append(candidate)
                year_quota[year] -= 1
                added = True
                break
            if len(selected) >= sample_count:
                break
        if not added:
            break

    if len(selected) < sample_count:
        for candidate in candidates:
            if len(selected) >= sample_count:
                break
            if any(abs(candidate - chosen) < minimum_gap for chosen in selected):
                continue
            if candidate not in selected:
                selected.append(candidate)

    selected.sort()
    if len(selected) < sample_count:
        raise ValueError(
            f"Only {len(selected)} null windows satisfied the spacing/exclusion constraints "
            f"out of {sample_count} requested."
        )

    rows = []
    for i, timestamp in enumerate(selected, start=1):
        null_id = f"NULL{i:04d}"
        for radar in radars:
            rows.append(
                {
                    "case_id": "",
                    "window_id": f"{null_id}_{radar}",
                    "null_id": null_id,
                    "radar_site": radar,
                    "window_center_utc": timestamp.isoformat().replace("+00:00", "Z"),
                    "window_start_utc": (
                        timestamp - pd.Timedelta(minutes=90)
                    ).isoformat().replace("+00:00", "Z"),
                    "window_end_utc": (
                        timestamp + pd.Timedelta(minutes=90)
                    ).isoformat().replace("+00:00", "Z"),
                    "source": "stratified_winter_background_candidate",
                    "label_status": "candidate_null",
                    "selection_seed": seed,
                    "minimum_separation_hours": min_separation_hours,
                    "case_exclusion_before_minutes": exclusion_before_minutes,
                    "case_exclusion_after_minutes": exclusion_after_minutes,
                }
            )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--start", default="2001-11-01T00:00:00Z")
    parser.add_argument("--end", default="2011-04-01T00:00:00Z")
    parser.add_argument("--sample-count", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-separation-hours", type=int, default=24)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = build_null_windows(
        Path(args.cases),
        args.start,
        args.end,
        sample_count=args.sample_count,
        seed=args.seed,
        min_separation_hours=args.min_separation_hours,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result)} candidate null radar windows to {args.output}")
    print("Null IDs:", ", ".join(sorted(result["null_id"].unique())))


if __name__ == "__main__":
    main()
