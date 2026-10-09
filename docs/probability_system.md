# BTV Snow Squall Probability System

## Product concept

The operational product should behave like an object-based nowcasting system:

**detect → track → characterize → predict → update → display**

A storm is not assigned one permanent probability. Every radar scan produces a new feature vector for each tracked object, and the model recomputes its probability from the current state plus recent evolution.

This is intentionally analogous to the object-based architecture used by ProbSevere: ProbSevere identifies and tracks radar-defined storm objects and combines storm attributes with environmental information to produce storm-centric probabilities. NOAA documentation describes ProbSevere v3 as object-based, with predictions updated every two minutes, and the published v3 paper describes storm-object tracking and machine-learning predictors. citeturn2search5turn2search9

## Proposed BTV Snow Squall object

Each active object should contain:

- track ID
- current centroid and polygon
- motion vector
- radar intensity
- vertical structure
- dual-pol structure
- MRMS context
- environmental context
- surface observations near the object
- current snow-squall probability
- probability history
- data quality/confidence flags

## What the model should learn

The model should learn the interaction:

**environment × storm structure × storm evolution**

The SNSQ parameter is one environmental predictor. It is not the output.

The Southern New England climatology identified 100 non-lake-effect events and used surface observations, composite radar and cell tracking, with individual cells tracked through time. It found four movement-based event types, emphasizing that squalls are not one identical radar morphology. citeturn0search0

The BTV study identified 36 snow squalls in northern New York and Vermont, including 21 affecting Burlington, with short-duration heavy/moderate snow and rapid visibility impacts. citeturn0search23

## Probability timeline

For every tracked object:

- T-30 to T-15: early signal
- T-15 to T-5: developing signal
- T-5 to onset: immediate pre-impact signal
- onset to peak: mature/impact phase
- post-peak: decay

The initial training target is:

P(snow squall onset or positive event within next 30 minutes | information available at scan time)

Later targets can include 15, 30, 45 and 60 minutes plus an impact/severity target.

## Critical training rule

Every training row represents what was knowable at that exact scan time. Future radar scans, future surface observations, future warning issuance, and future event labels can define the target, but must never enter the predictor vector.

## Display concept

The eventual operational interface should show:

- radar object polygon
- current probability
- probability trend
- track history
- current storm age
- motion
- key environmental drivers
- radar structure indicators
- data-quality/confidence indicator

A trend such as 12% → 28% → 51% is more informative operationally than a single static number because it shows the model's evolving assessment.

## Data construction

The BTV and Southern New England studies are initial positive-event seed populations, not the final training population. We should reconstruct each positive case at scan resolution and deliberately sample matched null/non-squall objects from the same cool-season radar environments.

That converts published case lists into a storm-centric machine-learning dataset capable of supporting real-time tracking and probability updates.

## Calibration plan (required before probability claims)

The hand-weighted radar/environment equation above is a temporary research
benchmark only. The intended live product is a supervised, calibrated,
object-based probability model inspired by ProbSevere's methodology, adapted to
snow squalls and the available BTV inputs.

### Predictors and exclusions

- Radar: KCXX/KTYX reflectivity and velocity, object morphology, intensity,
  gradients, motion, and scan-to-scan evolution.
- Environment: forecast-time RAP fields and physically derived parameters
  available to the object at that scan.
- Satellite: excluded from the initial model; evaluate separately only if a
  later controlled experiment demonstrates incremental value.
- Historical analog similarity: excluded from live predictors and scoring.
- Leakage exclusions: future observations, outcome/association labels, warning
  metadata, and any fields unavailable at prediction time.

### Training and calibration protocol

1. Define the positive target as a verified snow-squall onset/impact matched to
   an object, with explicit onset-time and spatial/temporal matching rules.
   Unknown outcomes remain unlabeled; negative examples require defensible
   non-event evidence.
2. Compare an interpretable logistic-regression baseline with a nonlinear
   tree-based candidate using identical case-grouped folds and predictors.
3. Generate out-of-fold predictions with all scans from the same storm/event
   confined to one fold. Also evaluate forward-in-time splits.
4. Fit a probability calibrator (initial candidates: sigmoid/Platt and
   isotonic) only from training-side out-of-fold predictions. Keep the final
   temporal/case-held-out test set untouched for calibration assessment.
5. Assess each 15/30/45/60-minute target independently using Brier score,
   reliability diagrams, PR-AUC, event detection, false alarms, and baseline
   comparisons. Report sample sizes and uncertainty; do not declare calibration
   successful solely because the training workflow completes.
6. Publish calibrated values only after sufficient independent labeled cases
   and acceptable held-out reliability. Until then, label outputs as
   experimental model estimates, not calibrated operational probabilities.

The existing training/evaluation scripts provide leakage controls, case-grouped
evaluation, and ROC-AUC/PR-AUC/Brier metrics, but the presence of those metrics
does not mean the deployed model is already calibrated. Calibration must be
implemented and independently tested as a distinct stage.

## Explicit research component equation

The current transparent component guidance score uses radar and environmental
evidence only, separately for 15, 30, 45, and 60 minutes. Each component is on a
0–100 scale:

```text
research_score_h = 0.50 × radar_score_h
                 + 0.50 × environment_score_h
```

Analog matching is intentionally excluded from both the score and the live model
inputs for now. Historical cases remain useful for supervised training and
independent verification, but nearest-neighbor similarity is not a live score
contributor.

The radar component combines reflectivity intensity (27% of radar score),
reflectivity contrast (16%), leading-edge reflectivity gradient (16%), velocity
contrast (16%), core fraction (8%), reflectivity growth (10%), and object
organization (7%). Missing radar ingredients are omitted and remaining
ingredient weights are renormalized.

The environmental component uses the repository's environment-risk features,
including instability, low-level moisture, low-level wind, lapse rate, and SNSQ,
with a snow-at-surface gate. At 30, 45, and 60 minutes, available RAP +30-minute
guidance contributes 40%, 60%, and 75% of the environmental score, respectively;
current conditions supply the remainder. At 15 minutes, current environment is
used.

**Important:** this weighted component score is transparent research guidance,
not a statistically calibrated probability. The separately trained machine
learning model must learn coefficients from verified historical labels and pass
case-held-out evaluation before its probabilities are described as validated.
