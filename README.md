# BTV Snow Squall

Experimental BTV CWA snow-squall detection/probability project.

## Phase 1: real-time Level II acquisition

The first test does **not** calculate snow-squall probability. It answers one question:

> How quickly can we obtain a newly completed KCXX or KTYX Level II volume from the public NOAA/Unidata AWS archive?

The watcher:

1. Looks for the newest completed volume for one radar.
2. Polls every 10 seconds.
3. Downloads each new volume once.
4. Records the radar volume time and local acquisition time.
5. Logs the resulting data age/latency.

NOAA/Unidata currently provides NEXRAD Level II in the public S3 bucket
`unidata-nexrad-level2` in `us-east-1`. The archive is updated as new data become
available.

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Test KCXX

From the `acquisition` directory:

```bash
cd acquisition
python kcxx_watcher.py
```

### Test KTYX

In a second terminal:

```bash
cd acquisition
python ktyx_watcher.py
```

### Or use the generic watcher

```bash
python radar_watcher.py --radar KCXX --poll-seconds 10
python radar_watcher.py --radar KTYX --poll-seconds 10
```

## Output

Raw Level II files are stored under:

```text
data/raw/KCXX/
data/raw/KTYX/
```

Logs are stored under:

```text
logs/kcxx_watcher.log
logs/ktyx_watcher.log
```

## Important architecture note

This first version uses S3 polling because it is easy to test and does not require
an AWS account.

For the low-latency production architecture, the acquisition layer can later be
changed to the NOAA/Unidata real-time Level II notification path (SNS/SQS) or the
real-time Level II chunks feed. The downstream processing interface should remain
the same.

## Planned next steps

- Verify actual acquisition latency.
- Read downloaded volumes with Py-ART.
- Extract BTV CWA-relevant radar fields.
- Add MRMS JSON precipitation-type information.
- Add existing RAP/MetPy SNSQ information.
- Build object detection and tracking.
- Develop and validate an experimental snow-squall probability model.
