# Snow Squall Label Policy — Dataset v1

## Core principle

The model must learn the combination of environment, storm structure, storm evolution, and observed impact, not the environmental Snow Squall Parameter alone.

A training row represents a tracked radar object at a specific scan time.

## Positive

Label snow_squall when multiple independent sources support a materially squall-like event. Evidence can include verified snow-squall documentation, an official SQW, radar structure/evolution consistent with a squall, and surface observations showing rapid visibility deterioration and/or strong wind.

An official SQW is supporting evidence, not an automatic positive label.

## Negative

Label null when there is adequate evidence that precipitation or convective structure did not produce a snow squall. Do not create negatives merely because an event was not warned.

## Uncertain

Use uncertain when evidence is insufficient or conflicting. These rows remain archived but are excluded from the initial supervised training set.

## Temporal labeling

Preserve verified onset and end, plus pre-onset, mature, and decay phases. This lets the model learn lead time rather than only classifying mature storms.

## Leakage controls

Future information such as verified onset/end time, future radar evolution, post-event surface observations, and future SQW issuance can be used for labels and evaluation windows, but never as predictors at prediction time.

## Confidence

high = multiple independent evidence sources agree.
medium = evidence supports the label but one major source is missing.
low = plausible classification requiring review.

## Initial modeling target

Probability that a radar object will meet the positive snow-squall definition within the next 30 minutes.
