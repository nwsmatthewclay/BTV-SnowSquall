"""Normalize persisted live-product timestamps to explicit UTC.

This migration is intentionally conservative. It changes only timestamp fields
that are already represented as UTC by the live worker; it does not alter radar
measurements, object identity, or scientific values.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def normalize_timestamp(value):
    if value is None:
        return value
    text = str(value).strip()
    if not text:
        return value
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_object(obj):
    if isinstance(obj, dict):
        return {
            key: (
                normalize_timestamp(value)
                if isinstance(value, str)
                and (key == "timestamp" or key.endswith("_utc"))
                else normalize_object(value)
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [normalize_object(value) for value in obj]
    return obj


def normalize_json_file(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_object(payload)
    path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return normalized


def normalize_jsonl_file(path: Path):
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(normalize_object(json.loads(line)))
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )
    return rows


def normalize_live_products(root: Path, sites=("KCXX", "KTYX")):
    results = {}
    for site in sites:
        site_result = {}
        for suffix in ("_state.json", "_objects.geojson", "_history.json"):
            path = root / f"{site}{suffix}"
            if path.exists():
                normalize_json_file(path)
                site_result[suffix] = True

        jsonl = root / f"{site}_history.jsonl"
        if jsonl.exists():
            rows = normalize_jsonl_file(jsonl)
            site_result["_history.jsonl"] = len(rows)

        results[site] = site_result
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="viewer/data/live")
    args = parser.parse_args()
    print(json.dumps(normalize_live_products(Path(args.root)), indent=2))


if __name__ == "__main__":
    main()
