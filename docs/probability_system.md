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
