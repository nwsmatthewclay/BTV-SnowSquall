# Hard-Negative Review and Promotion

This workflow keeps vigorous winter radar activity out of supervised-negative training until it has been explicitly reviewed.

## State machine

The review path is:

`winter_null_candidate` → `hard-negative candidate` → `reviewed_negative` **or** `contaminated_unknown` / `retain_candidate`

A hard-negative score is a **review-priority diagnostic**, not a truth label.

## Required reviewer decisions

Edit `data/reviews/snow_squall_hard_negative_review.csv` with one row per `null_id`:

- `review_status`: `pending` or `reviewed`
- `final_class`: `pending`, `reviewed_negative`, `contaminated_unknown`, or `retain_candidate`
- `radar_target_present`: `yes`, `no`, or `unknown`
- `event_evidence_present`: `yes`, `no`, or `unknown`
- `surface_evidence_interpreted`: `yes`, `no`, or `unknown`
- `reviewer`: reviewer identifier
- `reviewed_at_utc`: UTC timestamp
- `review_notes`: concise reasoning and any important object/scan references

## Training promotion gate

A window becomes a training negative only when all of these are true:

1. `review_status=reviewed`
2. `final_class=reviewed_negative`
3. `radar_target_present=no`
4. `event_evidence_present=no`
5. `reviewer` is populated
6. `reviewed_at_utc` is populated

`training_eligible` is derived by `scripts/build_hard_negative_review_packet.py`; it is not a free-form reviewer field.

The resulting `reviewed_negative_nulls.csv` is keyed by `null_id`, so all object timesteps belonging to that reviewed null window can be admitted consistently by the model-training scripts.

## Reviewer workflow

The automated queue is regenerated after expansion and persists new pending candidates to the review ledger. Existing decisions are preserved by `null_id`.

Do not mark a candidate as `reviewed_negative` merely because it lacks an official report. Radar reconstruction and independent event evidence must both be considered.

A reviewed negative can still show snow, low visibility, or gusts at the surface. Those observations are useful evidence for deciding whether an actual squall target was present; they are not automatic positive truth.

## Safety / reproducibility policy

No model score, hard-negative score, surface report, or archive-source absence can automatically create negative truth.

Every promoted negative retains:

- the original `null_id`
- hard-negative diagnostics
- peak radar/object pointer
- reviewer and review time
- reviewer notes
- explicit promotion reason

This keeps the negative population auditable and reversible.
