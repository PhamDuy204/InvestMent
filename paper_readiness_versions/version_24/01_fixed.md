# Fixed Facts — V24

1. H21-C passed the exact predictive gate committed in V21 before outcomes.
2. The fixed economic mapping is **raw** `sign(ret_4)*oi_log_change_1h`; do not rescale, winsorize, rank-normalize, threshold, or combine it with H12 before the first corrected replay.
3. Use the exact inherited V4/V11 causal universe, decision timestamps, frozen optimizer/execution semantics, costs, funding, fold resets and final unwind.
4. Compare against corrected Ridge H12 under the same 10bps replay.
5. Mechanism attempts are now 3/3; development configuration/mechanism count is 7 including four earlier fixed model configurations.
6. Passing predictive diagnostics does not authorize trial 871, paper trading, RL, HPO or leverage increase.
