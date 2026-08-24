# Methods / Math — V18

Let `x_t` contain only features available at decision time `t`, and let

`y_t = residual_return(t+1 open -> t+12 horizon)`

for the inherited H12 target.

## Development information boundary

`information_time <= 2026-08-20 23:59:59 UTC`.

Because H12 requires twelve future hours to mature, the latest labeled development decision in the constructed panel is `2026-08-20 11:00 UTC`.

## Chronological validation

For each split, training timestamps precede validation timestamps, with a 12-hour purge between them. No random shuffling is allowed.

## Leakage-safe stacking

For each outer-development training block:

1. generate base-model predictions only on later chronological inner folds;
2. fit the Ridge meta-learner only on these out-of-fold predictions;
3. refit the fixed base learners on the full outer-training block;
4. score the later outer-development block.

The fixed base learners are Ridge, HistGradientBoosting and ExtraTrees. No parameter search was performed.

## Interpretation rule

A model-family improvement must be stable across chronological slices, not merely have a better aggregate number. Probe economics are not promotion evidence until exact corrected execution semantics are reconciled.
