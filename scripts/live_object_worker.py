"""Near-real-time object worker.

Polls the same public NEXRAD archive as the acquisition watcher, downloads a
new volume when needed, and immediately processes it into persistent tracked
objects. Acquisition and science processing remain separate modules.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone

from acquisition.radar_watcher import (
    find_newest_volume,
    find_recent_volumes,
    make_s3_client,
    download_volume,
    setup_logging,
    utc_now,
)
from scripts.process_live_volume import process_volume


def select_volumes(
    recent: list[tuple[str, datetime]],
    since: datetime | None,
    max_volumes_per_run: int,
    prefer_latest: bool = False,
) -> list[tuple[str, datetime]]:
    """Choose a bounded chronological batch without collapsing tracks to one scan.

    When the worker is behind, retain the newest bounded batch in chronological
    order. This skips an old backlog but still gives the tracker multiple
    consecutive observations to associate, unlike selecting only the final scan.
    A fresh state is seeded with the newest bounded batch for the same reason.
    """
    recent = list(recent)
    if not recent:
        return []
    limit = max(1, int(max_volumes_per_run))
    if prefer_latest:
        return [recent[-1]]

    backlog_minutes = None
    if since is not None:
        try:
            backlog_minutes = max(
                0.0,
                (recent[-1][1] - since).total_seconds() / 60.0,
            )
        except (AttributeError, TypeError):
            backlog_minutes = None

    if since is None or (backlog_minutes is not None and backlog_minutes > 15.0):
        return recent[-limit:]
    return recent[:limit]


def run(
    radar: str,
    poll_seconds: int,
    max_polls: int | None,
    state: Path,
    output: Path,
    history_jsonl: Path | None,
    history_csv: Path | None,
    max_volumes_per_run: int = 2,
    prefer_latest: bool = False,
):
    setup_logging(radar)
    logging.info("=" * 72)
    logging.info("BTV SNOW SQUALL - %s LIVE OBJECT WORKER", radar)
    logging.info("Poll interval: %s seconds", poll_seconds)
    logging.info("Object output: %s", output)
    logging.info("Tracker state: %s", state)
    logging.info("=" * 72)

    s3 = make_s3_client()
    last_key = None
    polls = 0

    while max_polls is None or polls < max_polls:
        polls += 1
        try:
            persisted_processed = set()
            persisted_last_scan = None
            if state.exists():
                try:
                    persisted = json.loads(state.read_text(encoding="utf-8"))
                    persisted_processed = set(persisted.get("processed_sources", []))
                    persisted_last_scan = persisted.get("last_scan_time_utc")
                except Exception:
                    logging.warning("Could not read persisted worker state; continuing.")

            since = None
            if persisted_last_scan:
                try:
                    since = datetime.fromisoformat(
                        str(persisted_last_scan).replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except (TypeError, ValueError):
                    since = None

            # Research replay can catch up chronologically, but operational live
            # mode should prioritize latency. When explicitly requested, use the
            # newest unprocessed volume so a slow science pass does not leave the
            # viewer permanently behind the radar feed.
            recent = find_recent_volumes(s3, radar, since=since, lookback_hours=2)
            if not recent:
                newest = find_newest_volume(s3, radar)
                if newest is None:
                    logging.warning("No recent %s volumes found.", radar)
                else:
                    key, volume_time = newest
                    if key not in persisted_processed and key != last_key:
                        recent = [(key, volume_time)]

            # Preserve multiple consecutive observations even during recovery.
            # When far behind, process the newest bounded batch in chronological
            # order; the live radar image is published independently, so the
            # object tracker does not need to discard all but one scan.
            recent = select_volumes(
                recent,
                since,
                max_volumes_per_run,
                prefer_latest=prefer_latest,
            )

            if not recent:
                logging.info("No unprocessed %s volumes; waiting.", radar)
            else:
                for key, volume_time in recent:
                    if key in persisted_processed or key == last_key:
                        continue
                    logging.info(
                        "Processing %s volume: %s | radar time=%s",
                        radar, key, volume_time.isoformat()
                    )
                    path = download_volume(s3, radar, key, volume_time)
                    changed = process_volume(
                        path,
                        state,
                        output,
                        history_jsonl_path=history_jsonl,
                        history_csv_path=history_csv,
                    )
                    logging.info(
                        "Processed=%s | source=%s | output=%s",
                        changed, path.name, output
                    )
                    last_key = key
                    persisted_processed.add(key)

            if max_polls is not None and polls >= max_polls:
                break
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            logging.info("Stopped by user.")
            break
        except Exception:
            logging.exception("Live worker error; retrying after 5 seconds.")
            time.sleep(5)

    logging.info("Live object worker finished after %d poll(s).", polls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--radar", required=True, choices=("KCXX", "KTYX"))
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--max-polls", type=int, default=None)
    parser.add_argument("--state", default="data/derived/live_tracker_state.json")
    parser.add_argument("--output", default="data/derived/live_objects.geojson")
    parser.add_argument("--history-jsonl", default=None)
    parser.add_argument("--history-csv", default=None)
    parser.add_argument(
        "--max-volumes-per-run",
        type=int,
        default=2,
        help="Maximum unprocessed Level-II volumes to process per scheduled run.",
    )
    parser.add_argument(
        "--prefer-latest",
        action="store_true",
        help="Operational mode: process the newest unprocessed volume instead of catching up the oldest backlog first.",
    )
    args = parser.parse_args()
    run(
        args.radar,
        max(2, args.poll_seconds),
        args.max_polls,
        Path(args.state),
        Path(args.output),
        Path(args.history_jsonl) if args.history_jsonl else None,
        Path(args.history_csv) if args.history_csv else None,
        max_volumes_per_run=max(1, args.max_volumes_per_run),
        prefer_latest=args.prefer_latest,
    )


if __name__ == "__main__":
    main()
