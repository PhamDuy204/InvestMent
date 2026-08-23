# Minimal Plan Toward Paper Readiness — V14

1. Do not change H12 or strategy code yet.
2. Audit a small deterministic sample of official historical Binance `bookDepth` across all three fold ranges and several liquid/less-liquid symbols. Use the same checks everywhere.
3. Reject the source if material timestamp/bucket/implied-price integrity problems appear; do not special-case bad dates.
4. If the source passes, download only the development dates/symbols actually needed by the existing decision panel and derive one fixed depth-asymmetry feature using a tiny data-prep path or existing tooling.
5. Run one data-level development diagnostic first. No strategy replay unless the direction/effect is stable enough to justify it.
6. If a mechanism survives, then reconcile V11 runtime, integrate through the shared feature/replay flow with one focused test, and run full verification.
7. Trial 871 stays blocked behind immutable candidate freeze, predeclaration, deterministic methodology audit, council review, proven untouched eligibility, and local==remote SHA.
8. Start paper simulation only if `READY_TO_START_PAPER=true`; never authorize live/private trading.
