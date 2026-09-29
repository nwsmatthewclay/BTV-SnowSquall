# Models

Trained model binaries are generated artifacts and must not be committed until a reproducible release process is established.

## Current research baseline

The current training workflow uses a gradient-boosted tree baseline with case-or-null grouped out-of-fold evaluation. Forecast-time predictors are built with an explicit current_and_past_only policy so future labels and outcomes are blocked from the predictor set.

Training writes:

- baseline_model.joblib
- oof_predictions.csv
- metrics.json

The metrics report records the dataset revision, predictor columns, training groups, case-held-out evaluation status, and the operational release status.

## Operational release policy

Newly trained models are candidate_only by default. A candidate model may be used for offline replay, diagnostics, and independent validation, but it is not eligible to emit a live probability.

The live runtime adapter requires a valid model bundle, an explicit operational_release_status of released, and matching predictor columns.

This separation is intentional: a good pilot metric is not by itself an operational release. Independent validation on held-out modern cases and an explicit release decision remain separate steps.

## Future candidates

Random forest, calibrated gradient boosting, and ensemble approaches can be compared against the baseline only after the same grouped, leakage-safe verification framework is applied.

Every released model should record the dataset version, full predictor list, training and validation populations, code commit, and independent verification evidence.
