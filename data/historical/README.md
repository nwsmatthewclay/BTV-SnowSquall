# Historical Snow Squall Case Database

This directory is the source-of-truth event manifest for training and replay.

## Label policy

- verified: documented/validated snow-squall event
- candidate: plausible event awaiting verification
- negative: near-miss or non-squall case retained for false-alarm training
- unknown: outcome not yet established

Do not equate warning issuance with ground truth. Warning products are operational labels; the model should ultimately learn observed radar, environment, and surface evolution.

## Initial benchmark

Banacos, Loconto & DeVoir (2014) identified 36 snow squalls from ten cool seasons using KBTV, KMPV, and KMSS observations, including 21 at KBTV. The research criteria included visibility <= 0.8 km (0.5 mi), a preceding wind increase, a 190-360 degree wind direction, and radar confirmation of a narrow convective band.

The first commit contains the KBTV cases that could be cleanly extracted from the published table. Additional historical records will be added only after source reconciliation.

## Replay target

Every verified case will eventually become timestamped replay data:

T-60, T-50, ... T-10, T0, T+10 ...

Features must be restricted to information available at each replay timestamp. Peak-event values must not leak backward into the prediction window.

## Planned linked data

- KCXX and KTYX Level-II
- MRMS reflectivity/composite
- MRMS precipitation type
- METAR/ASOS
- MPING
- RAP environmental fields
- MetPy snow-squall diagnostics
- radar object tracks
- warning polygons/VTEC
- observed impacts
