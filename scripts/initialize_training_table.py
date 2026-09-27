"""Initialize an empty schema-controlled snow-squall training table."""
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "feature_schema.csv"
OUT = ROOT / "data" / "training" / "training_table.csv"

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with SCHEMA.open(newline="", encoding="utf-8") as f:
        fields = [row["field"] for row in csv.DictReader(f)]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(fields)
    print(f"Initialized {OUT} with {len(fields)} fields.")

if __name__ == "__main__":
    main()
