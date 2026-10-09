#!/usr/bin/env python3
"""Process one event-driven KCXX radar cycle.

KCXX is the reference scan for the cycle. KTYX is selected as the closest
available companion scan within the configured synchronization window; a
slightly newer KTYX volume is valid when its timestamp is closer than the
previous KTYX scan. Both exact source volumes are processed and used to build
the published mosaic.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from acquisition.radar_watcher import (
    download_volume,
    find_recent_volumes,
    make_s3_client,
)
from scripts.process_live_volume import process_volume


def parse_time(raw: str) -> datetime:
    value = str(raw).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_volume_candidates(raw_root: Path, radar: str, target: datetime, tolerance_minutes: float) -> list[tuple[str, datetime]]:
    """Find already-cached Level-II volumes before touching the archive."""
    result = []
    for path in (raw_root / radar).glob(f"{radar}*."):
        # Kept as a defensive placeholder; the precise filename parser below
        # handles both underscore and non-underscore archive naming.
        _ = path
    from acquisition.radar_watcher import parse_volume_time
    for path in (raw_root / radar).glob("*"):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        t = parse_volume_time(path.name, radar)
        if t is None:
            continue
        if abs((t - target).total_seconds()) <= tolerance_minutes * 60:
            result.append((str(path), t))
    return sorted(result, key=lambda item: item[1])


def choose_kcxx(s3, target: datetime, tolerance_minutes: float, raw_root: Path | None = None) -> tuple[str, datetime]:
    local = _local_volume_candidates(raw_root, "KCXX", target, tolerance_minutes) if raw_root else []
    if local:
        return min(local, key=lambda item: abs((item[1] - target).total_seconds()))

    candidates = find_recent_volumes(
        s3, "KCXX",
        since=target - timedelta(minutes=max(5.0, tolerance_minutes + 2.0)),
        lookback_hours=2,
    )
    if not candidates:
        # The archive can lag the real-time notification briefly.  Look across
        # the full recent window and select the closest scan.
        candidates = find_recent_volumes(s3, "KCXX", lookback_hours=2)
    if not candidates:
        raise RuntimeError("No recent KCXX archive volumes are available.")

    key, scan = min(candidates, key=lambda item: abs((item[1] - target).total_seconds()))
    delta = abs((scan - target).total_seconds()) / 60.0
    if delta > tolerance_minutes:
        raise RuntimeError(
            f"No KCXX archive volume within {tolerance_minutes:.1f} min of "
            f"{target.isoformat()}; nearest is {scan.isoformat()} ({delta:.1f} min)."
        )
    return key, scan


def choose_ktyx(s3, kcxx_time: datetime, max_age_minutes: float, raw_root: Path | None = None) -> tuple[str, datetime] | None:
    """Choose the closest KTYX scan in a symmetric time window around KCXX."""
    tolerance_seconds = max(0.0, float(max_age_minutes)) * 60.0
    local = _local_volume_candidates(raw_root, "KTYX", kcxx_time, max_age_minutes) if raw_root else []
    if local:
        eligible = [
            item for item in local
            if abs((item[1] - kcxx_time).total_seconds()) <= tolerance_seconds
        ]
        if eligible:
            return min(eligible, key=lambda item: abs((item[1] - kcxx_time).total_seconds()))

    candidates = find_recent_volumes(
        s3,
        "KTYX",
        since=kcxx_time - timedelta(minutes=max_age_minutes),
        lookback_hours=2,
    )
    eligible = [
        item for item in candidates
        if abs((item[1] - kcxx_time).total_seconds()) <= tolerance_seconds
    ]
    return min(eligible, key=lambda item: abs((item[1] - kcxx_time).total_seconds())) if eligible else None


def wait_for_kcxx(s3, target: datetime, tolerance_minutes: float, attempts: int, delay_seconds: int):
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            result = choose_kcxx(s3, target, tolerance_minutes)
            print(f"KCXX archive match on attempt {attempt}: {result[0]} {result[1].isoformat()}")
            return result
        except Exception as exc:
            last_error = exc
            print(f"KCXX archive not ready on attempt {attempt}/{attempts}: {exc}")
            if attempt < attempts:
                time.sleep(max(5, delay_seconds))
    raise RuntimeError(str(last_error))



def archive_live_radar_frame(live_root: Path, *, cycle_time: datetime) -> None:
    """Archive the exact radar mosaic produced for this synchronized cycle.

    Reflectivity history is versioned with the BTV winter reflectivity v2 palette.
    Older frames are discarded from the active manifest during palette migration
    so the viewer never mixes images rendered with different color scales.
    """
    mosaic_path = live_root / "radar_mosaic.json"
    if not mosaic_path.exists():
        return
    try:
        mosaic = json.loads(mosaic_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    products = mosaic.get("display_products") or {}
    image_name = products.get("clean_image") or mosaic.get("image") or "radar_mosaic_clean.png"
    image = live_root / str(image_name)
    if not image.exists() or image.stat().st_size == 0:
        print(f"Skipping radar-history archive: reflectivity image unavailable: {image}")
        return

    grid = mosaic.get("grid") or {}
    if str(grid.get("color_table") or "") != "BTV_WINTER_REFLECTIVITY_V2":
        print("Skipping radar-history archive: mosaic is not marked BTV_WINTER_REFLECTIVITY_V2.")
        return

    history = live_root / "radar_history"
    history.mkdir(parents=True, exist_ok=True)
    manifest_path = history / "manifest.json"

    try:
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists() else {}
        )
    except (OSError, json.JSONDecodeError):
        manifest = {}

    # One-time migration: old history images were rendered with earlier display
    # palettes. Remove those reflectivity PNGs from the active archive so the
    # timeline cannot jump between color tables.
    if manifest.get("reflectivity_palette") != "BTV_WINTER_REFLECTIVITY_V2" or manifest.get("reflectivity_palette_version") != "BTV_WINTER_REFLECTIVITY_V2":
        for old in history.glob("mosaic_*.png"):
            try:
                old.unlink()
            except OSError:
                pass
        manifest = {
            "version": 2,
            "retention_frames": 18,
            "interval_hint_minutes": 5,
            "reflectivity_palette": "BTV_WINTER_REFLECTIVITY_V2",
            "reflectivity_palette_version": "BTV_WINTER_REFLECTIVITY_V2",
            "frames": [],
        }

    stamp = cycle_time.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
    image_name = f"mosaic_{stamp}.png"
    shutil.copyfile(image, history / image_name)

    frame = {
        "timestamp": cycle_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "image": f"radar_history/{image_name}",
        "bounds": mosaic.get("bounds"),
        "palette": "BTV_WINTER_REFLECTIVITY_V2",
        "palette_version": "BTV_WINTER_REFLECTIVITY_V2",
    }

    # The archive filename has second resolution. If this workflow is
    # triggered twice during the same second, timestamps can differ by
    # milliseconds while the image path is identical. Deduplicate by both
    # timestamp and image path so one physical mosaic is one slider frame.
    frames = [
        f for f in (manifest.get("frames") or [])
        if isinstance(f, dict)
        and str(f.get("timestamp")) != frame["timestamp"]
        and str(f.get("image") or "").split("?")[0] != frame["image"]
        and str(f.get("palette") or "") == "BTV_WINTER_REFLECTIVITY_V2"
    ]
    frames.append(frame)

    def ts(item):
        try:
            return parse_time(item.get("timestamp")).timestamp()
        except Exception:
            return 0.0

    frames.sort(key=ts)
    cutoff = cycle_time.astimezone(timezone.utc).timestamp() - 100 * 60
    frames = [f for f in frames if ts(f) >= cutoff]
    manifest.update({
        "version": 2,
        "retention_frames": 18,
        "interval_hint_minutes": 5,
        "reflectivity_palette": "BTV_WINTER_REFLECTIVITY_V2",
        "reflectivity_palette_version": "BTV_WINTER_REFLECTIVITY_V2",
        "frames": frames,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

def write_event_metadata(live_root: Path, *, requested: datetime, kcxx: tuple[str, datetime], ktyx: tuple[str, datetime] | None):
    payload = {
        "mode": "event_driven",
        "requested_scan_time_utc": requested.isoformat().replace("+00:00", "Z"),
        "kcxx": {
            "source_file": kcxx[0],
            "scan_time_utc": kcxx[1].isoformat().replace("+00:00", "Z"),
        },
        "ktyx": (
            {
                "source_file": ktyx[0],
                "scan_time_utc": ktyx[1].isoformat().replace("+00:00", "Z"),
                "age_minutes": round((kcxx[1] - ktyx[1]).total_seconds() / 60.0, 2),
            }
            if ktyx else None
        ),
        "published_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = live_root / "event_cycle.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radar", default="KCXX", choices=("KCXX",))
    parser.add_argument("--scan-time", required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--live-root", type=Path, default=Path("viewer/data/live"))
    parser.add_argument("--kcxx-tolerance-minutes", type=float, default=3.0)
    parser.add_argument("--ktyx-max-age-minutes", type=float, default=8.0)
    parser.add_argument("--archive-attempts", type=int, default=6)
    parser.add_argument("--archive-delay-seconds", type=int, default=20)
    args = parser.parse_args()

    requested = parse_time(args.scan_time)
    args.raw_root.mkdir(parents=True, exist_ok=True)
    args.live_root.mkdir(parents=True, exist_ok=True)

    s3 = make_s3_client()
    kcxx = choose_kcxx(s3, requested, args.kcxx_tolerance_minutes, args.raw_root)
    if not kcxx:
        kcxx = wait_for_kcxx(s3, requested, args.kcxx_tolerance_minutes, args.archive_attempts, args.archive_delay_seconds)
    kcxx_path = download_volume(s3, "KCXX", *kcxx)

    # Select the closest synchronized KTYX scan. A newer KTYX timestamp is
    # acceptable within the tolerance; rejecting it can pin KTYX to the prior
    # volume whenever the two radars' scan schedules are offset.
    ktyx = choose_ktyx(s3, kcxx[1], args.ktyx_max_age_minutes, args.raw_root)
    ktyx_path = download_volume(s3, "KTYX", *ktyx) if ktyx else None
    if ktyx_path:
        print(f"KTYX companion: {ktyx[0]} {ktyx[1].isoformat()}")
    else:
        print("KTYX companion: unavailable within synchronization window; KCXX-only cycle.")

    process_volume(
        kcxx_path,
        args.live_root / "KCXX_state.json",
        args.live_root / "KCXX_objects.geojson",
        history_jsonl_path=args.live_root / "KCXX_history.jsonl",
        history_csv_path=Path("data/derived/KCXX_history.csv"),
    )

    if ktyx_path:
        process_volume(
            ktyx_path,
            args.live_root / "KTYX_state.json",
            args.live_root / "KTYX_objects.geojson",
            history_jsonl_path=args.live_root / "KTYX_history.jsonl",
            history_csv_path=Path("data/derived/KTYX_history.csv"),
        )

    # Force the existing mosaic builder to use these exact source files by
    # supplying temporary state files with last_source set to the selected
    # archive objects. The browser-facing renderer remains unchanged.
    with tempfile.TemporaryDirectory(prefix="btv-event-mosaic-") as tmp:
        tmp_path = Path(tmp)
        kcxx_state = tmp_path / "KCXX_state.json"
        ktyx_state = tmp_path / "KTYX_state.json"
        kcxx_state.write_text(json.dumps({"last_source": kcxx_path.name, "force_source": True}) + "\n", encoding="utf-8")
        ktyx_state.write_text(
            json.dumps({"last_source": ktyx_path.name, "force_source": True}) + "\n" if ktyx_path else "{}\n",
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            "scripts/build_live_radar_mosaic.py",
            "--raw-root", str(args.raw_root),
            "--kcxx-state", str(kcxx_state),
            "--ktyx-state", str(ktyx_state),
            "--output-image", str(args.live_root / "radar_mosaic.png"),
            "--output-json", str(args.live_root / "radar_mosaic.json"),
        ]
        print("Building synchronized radar mosaic:", " ".join(cmd))
        subprocess.run(cmd, check=True)

    cycle_time = max(kcxx[1], ktyx[1] if ktyx else kcxx[1])
    archive_live_radar_frame(args.live_root, cycle_time=cycle_time)
    write_event_metadata(args.live_root, requested=requested, kcxx=kcxx, ktyx=ktyx)

    print("EVENT CYCLE COMPLETE")
    print("Requested:", requested.isoformat())
    print("KCXX:", kcxx[1].isoformat())
    print("KTYX:", ktyx[1].isoformat() if ktyx else "unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
