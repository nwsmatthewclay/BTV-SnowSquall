import json
import os
from pathlib import Path

from scripts.build_release_manifest import build_manifest


def test_release_manifest_contains_reproducible_file_hashes(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    payload = tmp_path / "data" / "example.txt"
    payload.write_text("snow squall\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_REF_NAME", "test")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")

    manifest = build_manifest(tmp_path, ["data"])
    assert manifest["manifest_version"] == "release_manifest_v1"
    assert manifest["repository_commit"] == "abc123"
    assert manifest["file_count"] == 1
    assert manifest["files"][0]["path"] == "data/example.txt"
    assert len(manifest["files"][0]["sha256"]) == 64
    assert manifest["total_size_bytes"] == payload.stat().st_size
