"""Cluster archived BTV Snow Squall Warning products into storm episodes.

This is a review aid only. It does not create truth labels or promote cases.
Warnings that overlap or occur within the episode gap threshold are grouped.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def cluster(df: pd.DataFrame, gap_minutes: int = 30) -> pd.DataFrame:
    if df.empty:
        return df.assign(episode_id=pd.Series(dtype=str))

    data = df.copy()
    data["issue_dt"] = pd.to_datetime(data["issue"], utc=True, errors="coerce")
    data["expire_dt"] = pd.to_datetime(data["expire"], utc=True, errors="coerce")
    data = data.dropna(subset=["issue_dt", "expire_dt"]).sort_values(
        ["issue_dt", "expire_dt", "event_id"]
    )

    episodes = []
    episode_num = 0
    current_end = None
    current_start = None

    for idx, row in data.iterrows():
        issue = row["issue_dt"]
        expire = row["expire_dt"]
        starts_new = (
            current_end is None
            or issue > current_end + pd.Timedelta(minutes=gap_minutes)
        )
        if starts_new:
            episode_num += 1
            current_start = issue
            current_end = expire
        else:
            current_end = max(current_end, expire)
        episodes.append((idx, episode_num, current_start))

    mapping = pd.DataFrame(
        episodes,
        columns=["_idx", "episode_num", "episode_start"],
    ).set_index("_idx")
    data = data.join(mapping)
    data["episode_id"] = data["episode_start"].dt.strftime("SQE%Y%m%dT%H%MZ")

    summary = (
        data.groupby(
            ["episode_id", "episode_start"],
            as_index=False,
        )
        .agg(
            warning_count=("event_id", "count"),
            first_warning_issue=("issue_dt", "min"),
            last_warning_expire=("expire_dt", "max"),
            years=("year", lambda s: ",".join(sorted({str(int(x)) for x in s}))),
        )
        .sort_values("episode_start")
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gap-minutes", type=int, default=30)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    result = cluster(df, args.gap_minutes)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    print(result.to_string(index=False))
    print(f"Clustered {len(df)} warning products into {len(result)} episodes.")


if __name__ == "__main__":
    main()
