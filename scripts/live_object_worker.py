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

from acquisition.radar_watcher import (
    find_newest_volume,
    make_s3_client,
    download_volume,
    setup_logging,
    utc_now,
)
from scripts.process_live_volume import process_volume


def run(radar: str, poll_seconds: int, max_polls: int | None, state: Path, output: Path):
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
            newest = find_newest_volume(s3, radar)
            if newest is None:
                logging.warning("No recent %s volumes found.", radar)
            else:
                key, volume_time = newest
                persisted_processed = set()
                if state.exists():
                    try:
                        persisted = json.loads(state.read_text(encoding="utf-8"))
                        persisted_processed = set(persisted.get("processed_sources", []))
                    except Exception:
                        logging.warning("Could not read persisted worker state; continuing.")
                if key in persisted_processed:
                    logging.info("Newest %s volume already processed: %s", radar, key)
                    last_key = key
                elif key != last_key:
                    logging.info(
                        "New %s volume: %s | radar time=%s",
                        radar, key, volume_time.isoformat()
                    )
                    path = download_volume(s3, radar, key, volume_time)
                    changed = process_volume(path, state, output)
                    logging.info(
                        "Processed=%s | source=%s | output=%s",
                        changed, path.name, output
                    )
                    last_key = key
                else:
                    logging.info("No newer %s volume; waiting.", radar)

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
    args = parser.parse_args()
    run(
        args.radar,
        max(2, args.poll_seconds),
        args.max_polls,
        Path(args.state),
        Path(args.output),
    )


if __name__ == "__main__":
    main()
