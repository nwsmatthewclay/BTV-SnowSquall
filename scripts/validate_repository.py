"""Lightweight foundation validation."""
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
required = ["config/dataset_config.yaml", "schema/feature_schema.csv",
            "schema/label_policy.md", "docs/architecture.md",
            "data/manifests/README.md"]
missing = [p for p in required if not (ROOT / p).exists()]
if missing:
    raise SystemExit("Missing required files: " + ", ".join(missing))
with open(ROOT / "config/dataset_config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)
for key in ("project", "archive", "radar", "sources", "labels"):
    if key not in config:
        raise SystemExit(f"dataset_config.yaml missing top-level key: {key}")
print("Repository foundation validation: OK")
