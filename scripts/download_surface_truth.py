"""Prepare the reproducible surface-truth staging area."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "surface_truth"

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    readme = OUT / "README.md"
    if not readme.exists():
        readme.write_text("# Surface Truth\n\nStore observation manifests and processing metadata here.\n", encoding="utf-8")
    print(f"Surface-truth staging directory ready: {OUT}")

if __name__ == "__main__":
    main()
