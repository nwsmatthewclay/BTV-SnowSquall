# Matched Null-Object Sampling

A useful snow-squall model cannot be trained from positive cases alone.

For every positive event, the reconstruction pipeline should sample candidate radar objects from nearby cool-season windows where no verified snow-squall event is occurring. Nulls should be drawn from the same radar domain and, where possible, similar environmental regimes.

## Rules

- Sample at scan/object level, not arbitrary pixels.
- Exclude the positive-event spatial and temporal footprint plus a configurable buffer.
- Prefer cool-season dates and the same radar coverage regime.
- Preserve the true class balance in the raw archive; apply class weighting or sampling only during training.
- Do not label an object negative merely because no Snow Squall Warning was issued.
- Require adequate surface/radar evidence before assigning a hard negative.
- Keep uncertain objects in the archive but exclude them from the initial supervised fit.

## Why this matters

The model is intended to learn the distinction between a genuinely evolving snow-squall object and ordinary winter echoes that occur in similar environments. The published BTV study itself used a control dataset of non-event winter time steps, while the Southern New England study explicitly notes that its environmental patterns can occur without observed squalls.