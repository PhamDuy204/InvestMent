# Fixed / Proven in V11

1. **V10 closeout reproducibility fixed**: final V10 artifacts committed and local/remote synchronized before V11 started.
2. **Evidence boundary established**: trial-870 held-out is explicitly observed/development for V11; it is not reusable as fresh OOS evidence.
3. **Failure decomposition implemented** using the shared replay/cost path rather than a new backtest engine.
4. **Cost attribution validated** including final unwind; transaction cost is not the originating failure.
5. **Causal regime localization corrected** to use existing causal state helpers rather than convenient hindsight labels.
6. **Root cause identified**: H12 loses before costs; alpha failure dominates.
7. **Fold-1 instability localized**: LONG fails broadly across causal trend/vol/activity/session states, so a tiny existing gate is not justified.
8. **Timing hypothesis bounded**: +60m is worse, but instant performance is already negative; timing is not the first problem to fix.
9. **Do-not-repeat discipline preserved**: no retuning of trial-870 flat-trend 0.5 scaling, no rescue around already observed result.
10. **Trial budget preserved**: trial 871 remains untouched.
11. **Safety boundary verified**: no live/private exchange mutation occurred; `LIVE_NOT_AUTHORIZED` retained.
