"""Build leakage-safe evolution features from an object table."""
from pathlib import Path
import argparse
import pandas as pd
from snow_squall.temporal import add_track_history_features

parser = argparse.ArgumentParser()
parser.add_argument("input")
parser.add_argument("output")
args = parser.parse_args()
frame = pd.read_csv(args.input)
result = add_track_history_features(frame)
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
result.to_csv(args.output, index=False)
print(f"Wrote {len(result):,} object-scan rows to {args.output}")
