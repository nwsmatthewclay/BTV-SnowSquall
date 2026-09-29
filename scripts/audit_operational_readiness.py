"""Validate the contract of a live snow-squall object product.

This is an engineering/data-integrity gate. It intentionally does not judge
forecast skill. The current worker is probability-free, so probability fields
must remain null and product metadata must explicitly say not_scored.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def validate(
    state_path: Path,
    geojson_path: Path,
    max_future_seconds: float = 120.0,
    max_age_minutes: float | None = None,
) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    geo = json.loads(geojson_path.read_text(encoding="utf-8"))

    assert geo.get("type") == "FeatureCollection", "GeoJSON must be a FeatureCollection"

    metadata = geo.get("metadata", {})
    assert (
        metadata.get("probability_status") == "not_scored"
    ), "Probability status must remain not_scored"
    assert state.get("last_source"), "Worker state is missing last_source"
    assert state.get("last_scan_time_utc"), "Worker state is missing last_scan_time_utc"
    assert "last_object_count" in state, "Worker state is missing last_object_count"

    assert str(state["last_scan_time_utc"]).endswith("Z"), "State scan timestamp must use explicit UTC suffix Z"
    assert str(metadata.get("scan_time_utc", "")).endswith("Z"), "GeoJSON scan timestamp must use explicit UTC suffix Z"

    state_time = parse_dt(state["last_scan_time_utc"])
    output_time = parse_dt(metadata.get("scan_time_utc"))
    assert (
        state_time is not None and output_time is not None
    ), "Output/state timestamps must be valid UTC datetimes"

    delta = abs((state_time - output_time).total_seconds())
    assert (
        delta <= max_future_seconds
    ), f"State/output scan times differ by {delta:.1f}s"

    now = datetime.now(timezone.utc)
    age_minutes = (now - output_time).total_seconds() / 60.0
    assert (
        (state_time - now).total_seconds() <= max_future_seconds
    ), "Product timestamp is in the future"

    if max_age_minutes is not None:
        assert (
            age_minutes <= max_age_minutes
        ), f"Product is stale: {age_minutes:.1f} minutes old > {max_age_minutes:.1f} minute limit"

    features = geo.get("features", [])
    assert (
        int(state["last_object_count"]) == len(features)
    ), "State object count does not match GeoJSON"

    invalid_geometry = 0
    invalid_probability = 0
    invalid_timestamp = 0
    out_of_domain = 0

    for feature in features:
        props = feature.get("properties", {})
        geometry = feature.get("geometry")

        if not geometry or geometry.get("type") != "Polygon":
            invalid_geometry += 1

        for key in (
            "probability_15min",
            "probability_30min",
            "probability_45min",
            "probability_60min",
        ):
            value = props.get(key)
            if value is not None and not (0.0 <= float(value) <= 1.0):
                invalid_probability += 1

        raw_ts = props.get("timestamp")
        if not str(raw_ts).endswith("Z"):
            invalid_timestamp += 1
        ts = parse_dt(raw_ts)
        if ts is None:
            invalid_timestamp += 1
        elif abs((ts - output_time).total_seconds()) > max_future_seconds:
            invalid_timestamp += 1

        lat = props.get("centroid_lat")
        lon = props.get("centroid_lon")
        if lat is not None and lon is not None:
            lat = float(lat)
            lon = float(lon)
            if not (40.0 <= lat <= 47.0 and -79.0 <= lon <= -68.0):
                out_of_domain += 1

    assert invalid_geometry == 0, f"{invalid_geometry} live objects have non-Polygon geometry"
    assert invalid_probability == 0, f"{invalid_probability} invalid probability values found"
    assert invalid_timestamp == 0, f"{invalid_timestamp} invalid object timestamps found"
    assert out_of_domain == 0, f"{out_of_domain} object centroids outside the BTV-domain guard"

    return {
        "status": "ready_for_unscored_live_object_delivery",
        "probability_status": metadata["probability_status"],
        "scan_time_utc": output_time.isoformat(),
        "age_minutes": round(age_minutes, 2),
        "max_age_minutes": max_age_minutes,
        "source_file": metadata.get("source_file"),
        "object_count": len(features),
        "geometry_invalid": invalid_geometry,
        "probability_invalid": invalid_probability,
        "timestamp_invalid": invalid_timestamp,
        "centroids_outside_domain": out_of_domain,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="data/derived/live_tracker_state.json")
    parser.add_argument("--geojson", default="data/derived/live_objects.geojson")
    parser.add_argument("--max-future-seconds", type=float, default=120.0)
    parser.add_argument(
        "--max-age-minutes",
        type=float,
        default=None,
        help="Fail when the latest product is older than this many minutes.",
    )
    args = parser.parse_args()

    print(
        json.dumps(
            validate(
                Path(args.state),
                Path(args.geojson),
                max_future_seconds=args.max_future_seconds,
                max_age_minutes=args.max_age_minutes,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
