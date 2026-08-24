# Minimal Plan Toward Paper Readiness — V17

1. Keep the current L2 recorder running; do not restart it without operational need.
2. Do not write feature code: reuse persisted `top_of_book_imbalance` from `l2_shadow_v8.py`.
3. Wait for 7 contiguous calendar days satisfying the fixed coverage rule; hourly timestamps are the independent decision cadence for this diagnostic.
4. Do not inspect H12 outcomes before that development block closes.
5. When eligible, split development into two equal chronological halves and test only the fixed imbalance feature with no threshold grid.
6. If signs disagree across halves, aggregate development effect is non-positive, or rescue/tuning is required, retire the L2 family.
7. If development passes, enforce a 12h purge gap then keep the next 7 days untouched; freeze exact candidate/evaluation methodology before opening it.
8. Only then reconcile the V11 runtime if needed, run deterministic methodology audit/council gate, and consider trial 871 once.
9. Existing A1 readiness still requires the repository's stricter post-freeze forward gates, including 30 untouched calendar days; this V17 research split does not weaken them.
10. Never authorize live/private trading.
