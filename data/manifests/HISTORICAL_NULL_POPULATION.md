# Historical Null Population

The model must contain winter radar objects that did not become verified snow squalls. These are sampled from background winter windows rather than from inside positive event windows.

## Rules

- Candidate windows default to November 1 through March 31 of the Banacos control winter (2005-06).
- A 3-hour exclusion buffer is applied before and after every verified Banacos event onset.
- Candidate center times are spaced every 3 hours.
- Each selected center produces a 3-hour radar window (T-90 to T+90).
- candidate_null means the window passed temporal exclusion. It does not yet mean every radar object in the window is a verified negative.
- Object-level negative labels are assigned only after radar reconstruction and an observation/event check.
- Objects approaching a future verified event remain eligible for prospective positive labels and must not be relabeled as negatives.

This follows the object-based approach used in the southern New England climatology, where radar cells were individually tracked and short/noisy tracks were removed rather than treating an entire radar scene as one object.
