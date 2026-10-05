"""Acquire nearby historical ASOS/METAR evidence for null windows.

Null-window surface observations are diagnostic screening evidence only. They
never prove a window was a snow-squall negative, and absence of observations is
never treated as proof of absence.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from acquisition.asos_iem import request_observations


RADAR_STATIONS = {
    "KCXX": ("KPBG", "KBTV"),
    "KTYX": ("KMSS", "KMPV"),
}


def acquire(
    manifest_path: Path,
    output_root: Path,
    workers: int = 6,
    buffer_before_minutes: int = 90,
    buffer_after_minutes: int = 90,
) -> None:
    manifest = pd.read_csv(manifest_path)
    required = {"null_id", "radar_site", "window_center_utc"}
    missing = sorted(required - set(manifest.columns))
    if missing:
        raise ValueError(f"Null manifest missing columns: {missing}")

    rows = manifest.drop_duplicates(["null_id", "radar_site"]).copy()
    rows["window_center_utc"] = pd.to_datetime(
        rows["window_center_utc"], utc=True, errors="coerce"
    )
    rows = rows.dropna(subset=["window_center_utc"])

    jobs = []
    for row in rows.itertuples(index=False):
        stations = RADAR_STATIONS.get(str(row.radar_site).upper(), ())
        for station in stations:
            start = row.window_center_utc - pd.Timedelta(minutes=buffer_before_minutes)
            end = row.window_center_utc + pd.Timedelta(minutes=buffer_after_minutes)
            jobs.append((row.null_id, row.radar_site, station, start, end))

    output_root.mkdir(parents=True, exist_ok=True)
    errors = []
    metadata = []

    def run(job):
        null_id, radar_site, station, start, end = job
        try:
            frame = request_observations(station, start, end)
            frame["null_id"] = str(null_id)
            frame["radar_site"] = str(radar_site)
            frame["surface_station"] = station
            return job, frame, None
        except Exception as exc:
            return job, pd.DataFrame(), exc

    workers = max(1, min(int(workers), 12))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            (null_id, radar_site, station, start, end), frame, error = future.result()
            key = f"{null_id}__{radar_site}__{station}"
            if error is not None:
                errors.append({
                    "null_id": null_id,
                    "radar_site": radar_site,
                    "surface_station": station,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                })
                continue
            path = output_root / station / f"{null_id}__{radar_site}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index=False)
            metadata.append({
                "null_id": null_id,
                "radar_site": radar_site,
                "surface_station": station,
                "start_utc": start.isoformat().replace("+00:00", "Z"),
                "end_utc": end.isoformat().replace("+00:00", "Z"),
                "row_count": int(len(frame)),
                "output": str(path),
                "key": key,
            })

    pd.DataFrame(metadata).to_csv(
        output_root / "null_surface_download_manifest.csv", index=False
    )
    pd.DataFrame(
        errors,
        columns=[
            "null_id",
            "radar_site",
            "surface_station",
            "error_type",
            "error_message",
        ],
    ).to_csv(output_root / "null_surface_download_errors.csv", index=False)

    print(f"Null surface station jobs: {len(jobs)}")
    print(f"Successful surface files: {len(metadata)}")
    print(f"Surface failures: {len(errors)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    acquire(
        Path(args.manifest),
        Path(args.output),
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
