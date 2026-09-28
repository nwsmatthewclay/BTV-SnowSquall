from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]

def test_schema_exists_and_is_nontrivial():
    rows=list(csv.DictReader((ROOT/"schema/feature_schema.csv").open(encoding="utf-8")))
    assert len(rows) >= 60
    assert len({r["field"] for r in rows}) == len(rows)

def test_required_groups_are_present():
    rows=list(csv.DictReader((ROOT/"schema/feature_schema.csv").open(encoding="utf-8")))
    groups={r["group"] for r in rows}
    assert {"sounding","reflectivity","dualpol","mrms","evolution","surface_truth","label"} <= groups

def test_project_scaffolding_exists():
    for p in ["config/dataset_config.yaml","schema/label_policy.md","docs/architecture.md","docs/implementation_plan.md"]:
        assert (ROOT/p).exists()
