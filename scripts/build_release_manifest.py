"""Build a reproducibility manifest for a shareable dataset or viewer release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, selected_paths: list[str]) -> dict:
    files = []
    for relative in selected_paths:
        path = root / relative
        if not path.exists():
            continue
        if path.is_file():
            candidates = [path]
        else:
            candidates = sorted(p for p in path.rglob("*") if p.is_file())

        for item in candidates:
            rel = item.relative_to(root).as_posix()
            files.append({
                "path": rel,
                "size_bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            })

    files.sort(key=lambda row: row["path"])
    return {
        "manifest_version": "release_manifest_v1",
        "build_time_utc": datetime.now(timezone.utc).isoformat(),
        "repository_commit": os.environ.get("GITHUB_SHA"),
        "branch": os.environ.get("GITHUB_REF_NAME"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "future_information_policy": "artifact_manifest_only; does_not_modify_science_data",
        "file_count": len(files),
        "total_size_bytes": sum(row["size_bytes"] for row in files),
        "files": files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        required=True,
        help="Relative file or directory to include. Repeat for multiple paths.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = build_manifest(root, args.paths)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "file_count": manifest["file_count"],
        "total_size_bytes": manifest["total_size_bytes"],
        "repository_commit": manifest["repository_commit"],
    }, indent=2))


if __name__ == "__main__":
    main()
