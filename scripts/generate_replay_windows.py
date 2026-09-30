#!/usr/bin/env python3
"""Generate timestamped replay windows from the historical case manifest.

The output is intentionally label/provenance only. Meteorological features are
joined later from radar, METAR, MRMS, and RAP data. This prevents future/event-
peak information from leaking into a pre-event prediction timestamp.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default="data/historical/case_manifest.csv")
    p.add_argument("--output", default="data/historical/replay_windows.csv")
    p.add_argument("--pre-min", type=int, default=60)
    p.add_argument("--post-min", type=int, default=90)
    p.add_argument("--step-min", type=int, default=5)
    return p.parse_args()


def parse_event_time(row: dict[str, str]) -> datetime:
    return datetime.strptime(
        f"{row['event_date']} {row['event_time_utc']}",
        "%Y-%m-%d %H:%M",
    ).replace(tzinfo=timezone.utc)


def classify_phase(offset: int) -> str:
    if offset < 0:
        return "pre_event"
    if offset == 0:
        return "onset"
    return "post_event"


def main() -> None:
    args = parse_args()
    if args.step_min <= 0:
        raise SystemExit("--step-min must be > 0")
    if args.pre_min < 0 or args.post_min < 0:
        raise SystemExit("pre/post windows must be >= 0")

    rows: list[dict[str, str]] = []
    with Path(args.manifest).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            start = parse_event_time(row)
            for offset in range(-args.pre_min, args.post_min + 1, args.step_min):
                valid = start + timedelta(minutes=offset)
                rows.append(
                    {
                        "case_id": row["case_id"],
                        "event_start_utc": start.isoformat().replace("+00:00", "Z"),
                        "valid_time_utc": valid.isoformat().replace("+00:00", "Z"),
                        "offset_min": str(offset),
                        "phase": classify_phase(offset),
                        "classification": row["classification"],
                        "verification": row["verification"],
                        "source": row["source"],
                        "site": row["site"],
                    }
                )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id", "event_start_utc", "valid_time_utc", "offset_min", "phase",
        "classification", "verification", "source", "site",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} replay timestamps to {out}")


if __name__ == "__main__":
    main()
