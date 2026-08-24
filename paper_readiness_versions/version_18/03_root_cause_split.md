# Root Cause Split — V18

## Research blocker removed

V17 treated seven contiguous days of newly recorded L2 as the next research prerequisite. V18 separates research from paper evidence:

- **Model development:** historical/public information through 2026-08-20 is allowed immediately.
- **Untouched/paper evidence:** outcomes after 2026-08-20 remain reserved and must mature naturally.

This removes unnecessary wall-clock waiting without pretending historical development is fresh OOS evidence.

## Scientific result so far

The first complexity escalation did not rescue the core problem. Chronological stacking of Ridge + HistGB + ExtraTrees did not produce stable cross-sectional ranking improvement. HistGB has the least-bad rank diagnostic among the nonlinear bases, but the magnitude is very small and does not yet justify HPO or RL.

## Next root-cause action

Reconcile score evaluation with the corrected execution path before trying more model complexity. If fixed HistGB fails under that exact flow, prefer seeking materially new information rather than expanding the model zoo.
