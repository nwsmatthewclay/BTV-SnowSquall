# Historical to Operational Replay

The project now has a validation bridge between the historical case archive and
the eventual real-time processor.

## Purpose

A known historical radar case can be replayed one archived Level-II volume at a
time through the same process_live_volume.py path intended for operational
processing. This does not assign forecast probability.

The replay validates native Level-II reading, geolocation, object detection,
track continuity, motion, reflectivity evolution, environment attachment, and
state persistence while enforcing a one-scan-at-a-time information boundary.

## Usage

    python scripts/historical_operational_replay.py \
      --case-id BTV20060224 \
      --input-dir data/raw/positive_level2/BTV20060224 \
      --output-dir data/derived/operational_replays/BTV20060224

The output contains one GeoJSON file per processed scan, persistent replay
state, and replay_manifest.json.

## Scientific guardrail

The replay never loads the entire case into the processor before producing a
scan. The next scan is not available to the processor until the current output
has been written. This keeps the replay aligned with the intended operational
information boundary.

Replay is a pipeline validation tool, not independent model verification.
