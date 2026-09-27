# Git workflow for BTV-SnowSquall

## Branches
- `main`: stable baseline.
- `snow-squall-model-foundation`: current research branch and PR #1.

## Connector behavior
Edits made through the GitHub integration are real Git commits. Multiple file writes may therefore create multiple commits. That is not a failed push: the PR head should advance after successful writes.

For large future changes, we will batch logically related files and verify the branch head after the batch.

## Local troubleshooting
```bash
git fetch origin
git checkout snow-squall-model-foundation
git pull --ff-only origin snow-squall-model-foundation
```

Do not force-push this research branch unless its remote history has been inspected first.

## CI
Lightweight CI runs unit tests without requiring large radar archives. The scientific stack is isolated in `requirements-science.txt` so historical radar processing can be tested separately.
