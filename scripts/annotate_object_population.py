"""Attach reproducible case/null identifiers to reconstructed object scans."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _nonempty(value):
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def annotate(input_csv: Path, manifest_csv: Path, output_csv: Path):
    objects = pd.read_csv(input_csv)
    manifest = pd.read_csv(manifest_csv)

    required_manifest = {"radar_site", "window_start_utc", "window_end_utc"}
    missing = required_manifest - set(manifest.columns)
    if missing:
        raise ValueError(f"Manifest missing required columns: {sorted(missing)}")

    objects["scan_dt"] = pd.to_datetime(objects["scan_time_utc"], utc=True, errors="coerce")
    manifest["start_dt"] = pd.to_datetime(
        manifest["window_start_utc"], utc=True, errors="coerce"
    )
    manifest["end_dt"] = pd.to_datetime(
        manifest["window_end_utc"], utc=True, errors="coerce"
    )
    if "window_center_utc" in manifest.columns:
        manifest["center_dt"] = pd.to_datetime(
            manifest["window_center_utc"], utc=True, errors="coerce"
        )
    else:
        manifest["center_dt"] = manifest["start_dt"] + (
            manifest["end_dt"] - manifest["start_dt"]
        ) / 2

    ids, studies, case_ids, null_ids, window_ids, episode_ids, match_counts = (
        [], [], [], [], [], [], []
    )

    for _, obj in objects.iterrows():
        t = obj["scan_dt"]
        radar = obj.get("radar_site")
        matches = manifest[
            (manifest["radar_site"] == radar)
            & (manifest["start_dt"] <= t)
            & (manifest["end_dt"] >= t)
        ].copy()

        if matches.empty or pd.isna(t):
            ids.append(None)
            studies.append(None)
            case_ids.append(None)
            null_ids.append(None)
            window_ids.append(None)
            episode_ids.append(None)
            match_counts.append(0)
            continue

        # Windows can touch at their boundaries. Select the nearest center
        # deterministically so attribution does not depend on CSV row order.
        matches["center_distance_s"] = (
            (matches["center_dt"] - t).abs().dt.total_seconds()
        )
        matches = matches.sort_values(
            ["center_distance_s", "start_dt"], kind="stable"
        )
        row = matches.iloc[0]

        case_id = _nonempty(row.get("case_id"))
        null_id = _nonempty(row.get("null_id"))
        window_id = _nonempty(row.get("window_id"))
        population_id = case_id or null_id or window_id

        ids.append(population_id)
        studies.append(_nonempty(row.get("source")) or _nonempty(row.get("source_study")))
        case_ids.append(case_id)
        null_ids.append(null_id)
        window_ids.append(window_id)
        episode_ids.append(_nonempty(row.get("episode_id")))
        match_counts.append(len(matches))

    objects["population_id"] = ids
    objects["population_source"] = studies
    objects["case_id"] = case_ids
    objects["null_id"] = null_ids
    objects["window_id"] = window_ids
    objects["episode_id"] = episode_ids
    objects["annotation_match_count"] = match_counts
    objects.drop(columns=["scan_dt"], inplace=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    objects.to_csv(output_csv, index=False)

    print(f"Wrote {len(objects)} annotated object scans to {output_csv}")
    print("Annotated:", int(objects["population_id"].notna().sum()))
    print("Match-count distribution:")
    print(
        objects["annotation_match_count"]
        .value_counts(dropna=False)
        .sort_index()
        .to_string()
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    annotate(Path(args.input_csv), Path(args.manifest), Path(args.output))


if __name__ == "__main__":
    main()
