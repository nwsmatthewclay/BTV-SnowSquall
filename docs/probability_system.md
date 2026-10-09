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

## Explicit research component equation

The transparent component guidance score is computed separately for each lead time
(15, 30, 45, and 60 minutes). Each component is on a 0–100 scale:

```text
research_score_h = 0.50 × radar_score_h
                 + 0.35 × environment_score_h
                 + 0.15 × analog_score
```

The radar component combines reflectivity intensity (27% of radar score), reflectivity
contrast (16%), leading-edge reflectivity gradient (16%), velocity contrast (16%),
core fraction (8%), reflectivity growth (10%), and object organization (7%). Missing
radar ingredients are omitted and the remaining radar-ingredient weights are
renormalized.

The environmental component uses the repository's environment-risk features, including
instability, low-level moisture, low-level wind, lapse rate, and SNSQ, with a snow-at-
surface gate. At 30, 45, and 60 minutes, available RAP +30-minute guidance contributes
40%, 60%, and 75% of the environmental score, respectively; current conditions supply
the remainder. At 15 minutes, the current environment is used.

The analog component compares the object to labeled historical cases using standardized
feature distance and an inverse-distance-weighted estimate from up to eight nearest
matches. If no usable labeled analog catalog exists, the component is explicitly marked
`provisional_neutral` and assigned 50/100; that is a placeholder, not learned evidence.

**Important:** this weighted score is research guidance, not a calibrated probability.
The trained machine-learning candidate is a separate layer: a model is fit for each
onset horizon from numeric forecast-time predictors. The baseline uses median
imputation plus missingness indicators, feature standardization, and logistic
regression with class/case-scan balancing. Model-family evaluation also compares
gradient boosting, random forest, and extra trees on common case-held-out folds.
Labels, warnings, future observations, event association metadata, and other truth
fields must not be predictors. Cases—not individual scans—are held out together.
ROC-AUC and PR-AUC assess discrimination; Brier score assesses probability error.
Calibration and operational release require separate evidence and approval; a
successful training workflow alone does not make the output operational.
