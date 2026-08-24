# Open Problems — Ordered by Leverage

## P0 — Audit full-range Binance metrics continuity and semantics

Smallest falsifiable question:

> Can the official Binance USD-M daily `metrics` archive provide a causal, mechanically well-defined positioning/open-interest panel for the 21-symbol V11 universe across every historical DEVELOPMENT decision timestamp without outcome-dependent repair?

Before modeling:
- audit file existence and 5-minute timestamp continuity across the full old-fold date range;
- define causal hourly aggregation using only completed 5-minute rows strictly before each H12 decision;
- verify symbols/listing gaps explicitly rather than forward-filling fabricated history;
- document exact semantics of each candidate field.

## P1 — Choose one new metric mechanism only after P0

If P0 passes, test at most one predeclared mechanism first. Candidate families are open-interest change and trader-positioning imbalance. Do not grid transforms/thresholds or combine all metrics into a model before a simple directional relationship is established chronologically.

## P2 — Forward L2 remains validation/paper evidence

Keep collecting L2. It no longer blocks historical research and must not be used with post-2026-08-20 outcomes to tune V19.

## P3 — Model complexity

HistGB price-only rescue is rejected. No stacking/Optuna/RL unless a materially new causal signal first survives chronological development tests.

## P4 — Trial 871 / paper readiness

Still blocked behind a defensible mechanism, fixed candidate/config hash, predeclaration, untouched eligibility, deterministic audit, council methodology check, exact local==remote SHA, and required forward/paper evidence.
