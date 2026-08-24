# Open Problems — V21

## P0 — Test H21-A exactly once

Evaluate `crowd_short_contrarian` on the inherited historical DEVELOPMENT decision population.

Fixed pass gate:
- mean timestamp cross-sectional Spearman(feature, H12 holding return) > 0 in at least 2/3 inherited chronological folds;
- top-2 minus bottom-2 mean holding-return spread > 0 in at least 2/3 folds;
- aggregate mean timestamp Spearman > 0;
- no sign flipping or transformation search after seeing results.

If H21-A fails, record rejection before moving to H21-B.

## P1 — Corrected economic replay

A mechanism that passes P0 is not yet a candidate. First pass its raw score through the exact corrected V11 decision/execution flow with fixed 10bps cost and existing 1x caps.

## P2 — Untouched validation

All post-2026-08-20 outcomes remain reserved.
