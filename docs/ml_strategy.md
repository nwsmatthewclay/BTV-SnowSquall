# Machine Learning Strategy

## Research question

Can environmental conditions plus observed radar structure and evolution identify a snow squall before the highest-impact portion of the event?

## Feature hierarchy

### Environment
SNSQ, CAPE/CIN, DCAPE, PWAT, low-level RH/wind, lapse rates, shear, wet-bulb structure, frontogenesis, DCVA, omega and EPV.

### Radar structure
Reflectivity intensity, gradients, echo tops, vertical depth, object geometry, organization and motion.

### Dual-pol
ZDR, RHOHV, KDP and their spatial/vertical relationships.

### Evolution
10-minute and longer changes in object area, reflectivity, echo tops, orientation and motion.

### Surface/precipitation context
MRMS precipitation type/rate and ASOS/METAR visibility, snow and wind.

## Model ladder

1. Logistic regression — transparent reference.
2. Random forest — nonlinear interactions and feature importance.
3. Gradient-boosted trees — primary tabular candidate.
4. Calibrated ensemble — only after independent case validation.

Deep learning should not be the first model. We need a trustworthy event database before increasing model complexity.

## Targets

Initial: probability of positive snow-squall classification within 30 minutes.

Later: 15, 30, 45 and 60 minute lead-time targets, plus severity/impact targets.

## Validation

Split by complete event/case. Never randomly split adjacent scans from the same storm.

Track Brier score, reliability, ROC-AUC, PR-AUC, false-alarm behavior, missed-event behavior and lead-time distribution.

## Important distinction

The model should learn:

**environment × storm structure × storm evolution**

rather than simply relearning the Snow Squall Parameter.
