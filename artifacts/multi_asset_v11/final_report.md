# Investment V11 Final Report — Root-Cause-First Paper Readiness

Generated: `2026-08-23T17:31:26.313965+00:00`
V11 evidence/code HEAD entering closeout: `41b1cf6491171eca75a46cad362bd11a64b63799`
The exact final branch SHA is verified after this report is committed and is authoritative in PR #8 and the final handoff; a commit cannot self-contain its own SHA.

## Outcome

V11 ends in **VALID_DIAGNOSTIC_END / V11_NOT_READY_FOR_PAPER**. Trial 871 was not authorized and not consumed. No factor was admitted, no candidate was frozen, A1 did not start, `PAPER_VALIDATED=false`, and live authorization remains **LIVE_NOT_AUTHORIZED**.

The dominant failure is **ALPHA_FAILURE**. H12 held-out economics are already negative before transaction costs: aggregate net at 0bps is `-0.010609462857` and gross holding-return sum is `-0.007414934438`. Transaction costs deepen the loss to `-0.035286447021` at 10bps and `-0.059357346291` at 20bps, but cost is not the originating sign failure.

Fold 1 is the decisive temporal-instability event. Its pre-cost economics reverse from `0.163541028671` on chronological development/selection to `-0.050265741355` on observed held-out evaluation. Within fold 1, LONG gross contribution is about `-0.103922` while SHORT gross contribution is about `+0.052383`; LONG is negative across all observed causal trend, volatility, activity, and global-session states. No small existing causal gate identifies a fold-1-like failure without fitting the now-observed period.

The only causally supported timing comparison is 0m vs +60m. The +60m delay moves pre-cost aggregate net from `-0.010609462857` to `-0.015507135486` and raises wrong-side rate from `0.353675` to `0.485206`. Timing is harmful but minor/secondary to alpha/regime failure because the instantaneous aggregate edge is already negative.

## Required 38-answer handoff

1. **Exact V10 source SHA:** `bbed86901b01acf66698cd988c17945573ed984d`.
2. **Exact final V11 local SHA:** resolved after this report commit; the authoritative value is the final `v11-root-cause-paper-readiness` branch tip reported in PR #8/final handoff. Evidence/code HEAD entering closeout was `41b1cf6491171eca75a46cad362bd11a64b63799`.
3. **Exact final V11 remote SHA:** same resolution rule as #2; verified against `origin/v11-root-cause-paper-readiness` after closeout push.
4. **Local/remote synchronized?** Closeout requires exact equality; final handoff reports the observed equality after push/fetch.
5. **P1 conclusion:** H12 loses before costs. Aggregate held-out 0bps net `-1.060946%`, gross holding sum `-0.741493%`, 10bps net `-3.528645%`, 20bps net `-5.935735%`.
6. **Dominant failure:** ALPHA. Ranking: ALPHA=DOMINANT, REGIME=SECONDARY, COST=SECONDARY, TIMING=MINOR.
7. **What made fold 1 different?** A temporal directional sign reversal: selection 0bps `16.354103%` -> held-out 0bps `-5.026574%`. Fold-1 LONG loses across all causal trend/vol/activity/session states while SHORT remains positive.
8. **Signal decay:** `NO_MEANINGFUL_EDGE`; only 0m and +60m are supported. +60m worsens 0bps net by `-0.489767%` and wrong-side rate from `35.37%` to `48.52%`.
9. **V11 mechanisms considered:** cost/no-trade-band, timing/horizon, repeat flat-trend scaling, volatility/dispersion de-risking, blanket LONG suppression, and materially new directional-core evidence/replacement. The first five were rejected as wrong-root-cause, do-not-repeat, or non-causal; the last is a future research direction rather than a small V11 configuration.
10. **Selected mechanism and why:** NONE. Existing causal states do not isolate the temporal LONG failure; adding another H12 filter would be overfit-prone.
11. **DEVELOPMENT configurations actually tried:** `0`.
12. **Trial 871 authorized?** NO.
13. **Trial 871 consumed?** NO.
14. **Max performance trial:** `870`.
15. **Trial-871 predeclaration:** N/A; no `hypothesis_predeclaration_871.json` was created.
16. **Trial-871 PASS/FAIL:** N/A; it did not run.
17. **Temporal folds improved for 871:** N/A.
18. **871 baseline/candidate metrics:** N/A. Diagnostic H12 baseline for context: net10 `-0.035286447021`, Sharpe `-0.699873546093`, turnover `50.510530534383`, net20 `-0.059357346291`. No V11 candidate exists.
19. **Factor admitted?** NO.
20. **Candidate frozen?** NO.
21. **Candidate hash:** `null`.
22. **Multiple-testing statistics actually computable:** none for a promoted V11 candidate because no V11 candidate/trial 871 exists; provenance status is recorded in `multiple_testing.json`.
23. **DSR:** `NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE`; no V11 candidate exists and an aligned joint trial/return selection structure is not available for a defensible readiness statistic.
24. **PBO/CSCV/CPCV:** `NOT_COMPUTABLE_WITH_CURRENT_PROVENANCE`; no aligned V11 candidate-return/configuration matrix exists.
25. **READY_TO_START_PAPER:** FALSE.
26. **Readiness categories:** SOURCE_OF_TRUTH PASS; CAUSALITY PASS; SCIENCE FAIL; EXECUTION PASS; OPERATIONAL PASS; SAFETY PASS; FREEZE FAIL.
27. **Remaining blockers:** negative pre-cost H12 economics, fold-1 broad directional instability, no defensible small V11 mechanism, no admitted/frozen candidate, no trial-871 validation, and insufficient post-boundary H12 maturity at closeout.
28. **A1 started?** NO — `NOT_STARTED`.
29. **PAPER_VALIDATED:** FALSE.
30. **Recorder states at closeout snapshot:** L2 PID `2743466` RUNNING/alive=`True`, errors `0`, records `44688`; positioning PID `2750224` RUNNING/alive=`True`, errors `0`, rows `630`, expected interval 3600s. Neither recorder was restarted.
31. **Exact Qwen model used:** V11 did not invoke council because the trial-871 authorization gate was never reached. The inherited V10 council model was `qwen/qwen3.6-27b`.
32. **Qwen advisory result:** V11: NOT_RUN. Inherited V10: `SUPPORT_TEST / FATAL_NONE`; no V11 approval is claimed.
33. **MiroFish used?** NO. Existing replay/state diagnostics were sufficient to identify the root cause; scenario simulation would not repair missing directional alpha.
34. **Any live/private exchange mutation?** NO.
35. **Live authorization:** `LIVE_NOT_AUTHORIZED`.
36. **PR:** #8, base `v10-scientific-candidate`, head `v11-root-cause-paper-readiness`.
37. **GitHub Actions exact final SHA:** checked after the final report commit; the final handoff reports the observed conclusion and does not claim PASS before that check.
38. **Shortest defensible next action:** do not burn trial 871. Accumulate untouched post-boundary evidence and, in a new research version, investigate a materially new causal directional core/regime detector that can identify fold-1-like LONG failure without using fold identity or retuning prior failed H12 filters.

## Safety

No live order, cancellation, leverage/margin mutation, borrowing, repayment, transfer, withdrawal, or other private exchange mutation was executed. **LIVE_NOT_AUTHORIZED** remains immutable.
