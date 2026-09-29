"""Build a conservative null-object sampling manifest.

Null windows use a dedicated window_id. case_id is intentionally blank
for null samples so downstream case counts cannot confuse candidate-null windows
with historical verified cases.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from acquisition.historical_level2 import key_time, list_volume_keys, s3_client

import pandas as pd


def select_candidates(candidates, sample_count, rng, availability=None):
    """Select reproducible candidates, optionally requiring archive coverage."""
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    if availability is not None:
        shuffled = [candidate for candidate in shuffled if availability(candidate)]
    return sorted(shuffled[:sample_count])


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
    require_level2: bool = False,
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
    availability = None
    if require_level2:
        client = s3_client()
        day_cache = {}

        def has_archive_volume(timestamp):
            start_time = timestamp - pd.Timedelta(minutes=90)
            end_time = timestamp + pd.Timedelta(minutes=90)
            day = start_time.normalize()
            while day <= end_time.normalize():
                availability = {}
                for radar in radars:
                    cache_key = (radar, day.date())
                    if cache_key not in day_cache:
                        keys = list_volume_keys(client, radar, day.to_pydatetime())
                        day_cache[cache_key] = [key_time(key) for key in keys]
                    availability[radar] = any(
                        t is not None
                        and start_time.to_pydatetime() <= t <= end_time.to_pydatetime()
                        for t in day_cache[cache_key]
                    )
                if all(availability.values()):
                    return True
                day += pd.Timedelta(days=1)
            return False

        availability = has_archive_volume

    selected = select_candidates(
        candidates, sample_count, rng, availability=availability
    )
    if len(selected) < sample_count:
        raise RuntimeError(
            f"Only {len(selected)} archive-covered null windows available; "
            f"requested {sample_count}."
        )

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
                "archive_preflight": "level2_available" if require_level2 else "not_checked",
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
    parser.add_argument("--require-level2", action="store_true", help="Only select windows with archive volumes for every requested radar in the ±90-minute window.")
    parser.add_argument("--output", default="data/manifests/banacos_null_windows.csv")
    args = parser.parse_args()

    result = build_null_windows(
        Path(args.cases),
        args.start,
        args.end,
        seed=args.seed,
        sample_count=args.sample_count,
        radars=tuple(args.radars),
        require_level2=args.require_level2,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result)} candidate null radar windows to {args.output}")


if __name__ == "__main__":
    main()
