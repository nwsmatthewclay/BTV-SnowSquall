# Release Reproducibility

Shareable snow-squall datasets and viewers should be traceable to the exact
code revision that produced them.

Use `scripts/build_release_manifest.py` to hash selected generated
files/directories without including large raw-archive trees by accident.

Example:

    python scripts/build_release_manifest.py \
      --output data/derived/release_manifest.json \
      --path data/derived \
      --path viewer

In GitHub Actions, the manifest automatically records the repository commit,
branch, workflow run ID, UTC build time, file sizes, and SHA-256 hashes.

The manifest describes the artifacts; it does not alter scientific records or
bypass any data-quality or leakage guard.
