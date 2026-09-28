"""Attach reproducible case/null identifiers to reconstructed object scans."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd


def annotate(input_csv: Path, manifest_csv: Path, output_csv: Path):
    objects = pd.read_csv(input_csv)
    manifest = pd.read_csv(manifest_csv)
    objects["scan_dt"] = pd.to_datetime(objects["scan_time_utc"], utc=True, errors="coerce")
    manifest["start_dt"] = pd.to_datetime(manifest["window_start_utc"], utc=True)
    manifest["end_dt"] = pd.to_datetime(manifest["window_end_utc"], utc=True)

    ids = []
    studies = []
    case_ids = []
    null_ids = []
    for _, obj in objects.iterrows():
        t = obj["scan_dt"]
        radar = obj.get("radar_site")
        matches = manifest[
            (manifest["radar_site"] == radar)
            & (manifest["start_dt"] <= t)
            & (manifest["end_dt"] >= t)
        ]
        if matches.empty:
            ids.append(None)
            studies.append(None)
            case_ids.append(None)
            null_ids.append(None)
        else:
            row = matches.iloc[0]
            ids.append(row.get("case_id", row.get("null_id")))
            studies.append(row.get("source", row.get("source_study")))
            case_ids.append(row.get("case_id"))
            null_ids.append(row.get("null_id"))
    objects["population_id"] = ids
    objects["population_source"] = studies
    objects["case_id"] = case_ids
    objects["null_id"] = null_ids
    objects.drop(columns=["scan_dt"], inplace=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    objects.to_csv(output_csv, index=False)
    print(f"Wrote {len(objects)} annotated object scans to {output_csv}")
    print("Annotated:", int(objects["population_id"].notna().sum()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    annotate(Path(args.input_csv), Path(args.manifest), Path(args.output))


if __name__ == "__main__":
    main()
