"""Write a reproducibility freeze record for an independent reconstruction."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(paths: list[Path], output: Path) -> dict:
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        git_sha = None

    files = {}
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        files[str(path)] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }

    payload = {
        "purpose": "independent reconstruction freeze",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "training_eligible": False,
        "scoring_status": "not_scored",
        "files": files,
        "policy": "freeze_before_reconstruction;no_post_hoc_case_selection_or_tuning",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    build([Path(p) for p in args.paths], Path(args.output))


if __name__ == "__main__":
    main()
