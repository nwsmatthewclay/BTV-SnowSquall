"""Convert archived replay scores into the existing historical viewer GeoJSON contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


HORIZONS = (15, 30, 45, 60)


def build(base_dir: Path, timeline_path: Path, output_path: Path) -> dict:
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    by_key = {
        (str(row.get("timestamp")), str(row.get("track_id"))): row
        for row in timeline.get("records") or []
    }

    features = []
    for path in sorted(base_dir.glob("*.geojson")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for feature in payload.get("features") or []:
            cloned = json.loads(json.dumps(feature))
            props = cloned.setdefault("properties", {})
            key = (str(props.get("timestamp")), str(props.get("track_id")))
            score = by_key.get(key)
            if score:
                cumulative = score.get("cumulative_probabilities") or {}
                raw = score.get("raw_cumulative_probabilities") or {}
                interval = score.get("interval_probabilities") or {}
                props["research_probabilities"] = {
                    f"{h}min": cumulative.get(str(h))
                    for h in HORIZONS
                    if cumulative.get(str(h)) is not None
                }
                props["research_probabilities_raw"] = {
                    f"{h}min": raw.get(str(h))
                    for h in HORIZONS
                    if raw.get(str(h)) is not None
                }
                props["research_interval_probabilities"] = {
                    f"{h}min": interval.get(str(h))
                    for h in HORIZONS
                    if interval.get(str(h)) is not None
                }
                props["probability_projection"] = score.get("probability_projection")
                props["probability_mode"] = "research_replay"
                props["research_only"] = True
            features.append(cloned)

    features.sort(
        key=lambda f: (
            str((f.get("properties") or {}).get("timestamp", "")),
            str((f.get("properties") or {}).get("track_id", "")),
        )
    )
    site_values = sorted(
        {
            str((f.get("properties") or {}).get("radar_site"))
            for f in features
            if (f.get("properties") or {}).get("radar_site")
        }
    )
    metadata = {
        "mode": "historical_replay_viewer_case",
        "operational_release_status": "candidate_only_not_operational",
        "future_information_policy": "one_scan_at_a_time",
        "probability_status": "research_replay",
        "probability_projection": "isotonic_non_decreasing_horizon",
        "source_timeline": str(timeline_path),
        "source_replay_directory": str(base_dir),
        "radar_sites": site_values,
        "feature_count": len(features),
    }
    output = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": metadata,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = build(args.base_dir, args.timeline, args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
