"""Create the master case manifest used by every reconstruction stage."""
from pathlib import Path
import csv

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/manifests/case_manifest.csv"
FIELDS=["case_id","source_study","source_case_id","event_start_utc","event_end_utc","center_lat","center_lon","cwa","sqw_available","radar_available","surface_truth_available","environment_available","label_status","notes"]

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if not OUT.exists():
        with OUT.open("w",newline="",encoding="utf-8") as f: csv.writer(f).writerow(FIELDS)
        print(OUT)
    else: print(f"Exists: {OUT}")

if __name__=="__main__": main()
