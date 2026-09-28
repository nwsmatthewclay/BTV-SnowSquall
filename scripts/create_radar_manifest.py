"""Create the reproducible radar acquisition manifest skeleton."""
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "manifests" / "radar_manifest.csv"
FIELDS = ["case_id","radar_site","event_start_utc","event_end_utc","volume_time_utc","source_key","local_path","sha256","native_resolution","status","notes"]

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUT.exists():
        with OUT.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(FIELDS)
        print(f"Created {OUT}")
    else:
        print(f"Exists: {OUT}")

if __name__ == "__main__":
    main()
