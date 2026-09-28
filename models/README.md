# Models

Trained model binaries are generated artifacts and should not be committed until a reproducible release process is established.

Current baseline:

- logistic regression
- 30-minute probability target
- case-based chronological validation

Future candidates:

- random forest
- gradient-boosted trees
- calibrated ensemble

Every released model must record the dataset version, feature list, training cases, validation cases and code commit.
