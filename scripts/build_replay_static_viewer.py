"""Build the existing historical viewer contract around a candidate replay case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(case_id: str, radar_site: str, replay_case: Path, timeline: Path, frames_root: Path, output_dir: Path) -> dict:
    payload = json.loads(replay_case.read_text(encoding="utf-8"))
    timeline_payload = json.loads(timeline.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    case_dir = data_dir / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)

    case_file = case_dir / f"{case_id}_{radar_site}_replay.geojson"
    case_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    frame_manifest_path = frames_root / "data" / "cases" / f"{case_id}_{radar_site}" / "frames.json"
    frames = []
    bounds = None
    if frame_manifest_path.exists():
        frame_payload = json.loads(frame_manifest_path.read_text(encoding="utf-8"))
        frames = frame_payload.get("frames", [])
        bounds = frame_payload.get("bounds")

    features = payload.get("features") or []
    timestamps = sorted({
        str((f.get("properties") or {}).get("timestamp"))
        for f in features
        if (f.get("properties") or {}).get("timestamp")
    })
    track_count = len({
        str((f.get("properties") or {}).get("track_id"))
        for f in features
        if (f.get("properties") or {}).get("track_id") is not None
    })
    scored_features = sum(
        1
        for f in features
        if (f.get("properties") or {}).get("research_probabilities")
    )

    catalog = {
        "product": "BTV Snow Squall Historical Replay Explorer",
        "build_time_utc": timeline_payload.get("generated_utc"),
        "version": "0.1-research-replay",
        "data_status": "research_replay",
        "probability_status": "research_replay",
        "research_probability_status": "candidate_only_not_operational",
        "future_information_policy": "one_scan_at_a_time",
        "truth_note": "Historical replay probabilities are research diagnostics only and are not operational guidance or verified object-level truth.",
        "source_replay_timeline": str(timeline),
        "cases": [{
            "case_id": case_id,
            "radar_site": radar_site,
            "file": f"cases/{case_file.name}",
            "status": "historical_replay_research",
            "source_study": "Modern independent validation replay",
            "event_start_utc": None,
            "scan_count": len(timestamps),
            "track_count": track_count,
            "scored_feature_count": scored_features,
            "first_scan_utc": timestamps[0] if timestamps else None,
            "last_scan_utc": timestamps[-1] if timestamps else None,
            "radar_frames": frames,
            "radar_bounds": bounds,
        }],
        "replay_summary": {
            "timeline_records": len(timeline_payload.get("records") or []),
            "scored_features": scored_features,
            "future_information_policy": "one_scan_at_a_time",
            "probability_projection": "isotonic_non_decreasing_horizon",
        },
    }
    (data_dir / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--radar-site", required=True)
    parser.add_argument("--replay-case", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--frames-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    catalog = build(
        args.case_id,
        args.radar_site,
        args.replay_case,
        args.timeline,
        args.frames_root,
        args.output_dir,
    )
    print(json.dumps({
        "status": "pass",
        "cases": len(catalog["cases"]),
        "timeline_records": catalog["replay_summary"]["timeline_records"],
        "scored_features": catalog["replay_summary"]["scored_features"],
    }, indent=2))


if __name__ == "__main__":
    main()
