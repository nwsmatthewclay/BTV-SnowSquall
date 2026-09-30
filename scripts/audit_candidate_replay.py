"""Audit an offline learned-model replay package for beta smoke-test readiness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def audit_horizon(root: Path, horizon: int) -> dict:
    horizon_dir = root / f"{horizon}m"
    manifest_path = horizon_dir / "replay_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing replay manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("scan_count", 0) <= 0:
        raise ValueError(f"{horizon}m: no successful scans")
    if manifest.get("failed_scan_count", 0) != 0:
        raise ValueError(f"{horizon}m: replay contains failed scans")
    if manifest.get("continuity_broken"):
        raise ValueError(f"{horizon}m: replay continuity is broken")
    causality = manifest.get("causality_audit") or {}
    if causality.get("continuity_broken"):
        raise ValueError(f"{horizon}m: causality audit reports broken continuity")

    expected_field = f"probability_{horizon}min"
    wrong_fields = {f"probability_{h}min" for h in (15, 30, 45, 60) if h != horizon}
    score_count = 0
    metadata_scored = 0
    future_policy_ok = True

    for geojson_path in sorted(horizon_dir.glob("*.geojson")):
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        metadata = payload.get("metadata") or {}
        if metadata.get("future_information_policy") not in (None, "one_scan_at_a_time"):
            future_policy_ok = False
        if metadata.get("probability_status") == "scored":
            metadata_scored += 1
            if metadata.get("probability_mode") != "research_replay":
                raise ValueError(
                    f"{horizon}m: scored replay record is not marked research_replay in {geojson_path.name}"
                )
        if metadata.get("model_horizon_minutes") not in (None, horizon):
            raise ValueError(f"{horizon}m: wrong model_horizon_minutes in {geojson_path.name}")
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            value = props.get(expected_field)
            if value is not None:
                score_count += 1
                value = float(value)
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"{horizon}m: probability outside [0,1] in {geojson_path.name}")
            for field in wrong_fields:
                if props.get(field) is not None:
                    raise ValueError(f"{horizon}m: score leaked into {field} in {geojson_path.name}")

    if not future_policy_ok:
        raise ValueError(f"{horizon}m: future-information policy violation")
    if score_count == 0:
        raise ValueError(f"{horizon}m: no scored object records were produced")

    return {
        "horizon_minutes": horizon,
        "scan_count": int(manifest.get("scan_count", 0)),
        "object_scan_count": int(manifest.get("object_scan_count", 0)),
        "scored_scan_metadata_count": metadata_scored,
        "scored_object_count": score_count,
        "probability_status": manifest.get("probability_status"),
        "future_information_policy": "one_scan_at_a_time",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    rows = [audit_horizon(args.root, h) for h in (15, 30, 45, 60)]
    report = {"status": "pass", "horizons": rows}
    print(json.dumps(report, indent=2))
    (args.root / "beta_replay_audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
