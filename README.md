# BTV Snow Squall

Experimental BTV CWA snow-squall detection and probability project.

## Current architecture

The project is being built as a **living event/object dataset**, not as an SNSQ calculator.

The core training unit is:

> **tracked radar object × scan time**

Each row will combine environmental conditions, 3-D radar structure, storm evolution, dual-pol signatures, MRMS information, and independent event/surface truth.

### Data flow

acquisition → normalization → object detection → tracking → feature extraction → labeling → training table → model → verification

### Data layers

- NEXRAD Level II from KCXX and KTYX
- RAP environmental analyses and derived SNSQ
- MRMS precipitation/echo-top products
- ASOS/METAR/NCEI surface observations
- Official SQW/event documentation
- Published snow-squall case datasets/studies

### Initial prediction target

Probability that a tracked radar object will meet the positive snow-squall definition within the **next 30 minutes**.

Future lead-time targets can be added after the first baseline is validated.

## Repository structure

- `acquisition/` — near-real-time Level II acquisition
- `config/` — dataset and archive configuration
- `schema/` — feature schema and labeling policy
- `docs/` — architecture and implementation plan
- `scripts/` — reproducible dataset/manifest utilities
- `tests/` — automated smoke tests
- `data/` — local scientific data and manifests; large files are excluded from Git

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python scripts/initialize_training_table.py
```

GitHub Actions runs the smoke tests on pushes and pull requests.

## Modeling principles

The environmental Snow Squall Parameter is a predictor, not the answer.

Training/evaluation will:

1. Preserve complete case histories.
2. Use radar-object and temporal information.
3. Keep future information out of predictors.
4. Hold out complete events rather than random rows.
5. Evaluate calibration and lead time in addition to discrimination.

See `docs/architecture.md`, `docs/implementation_plan.md`, and `schema/label_policy.md`.
