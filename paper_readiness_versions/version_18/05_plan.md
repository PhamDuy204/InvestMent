# Plan — V18

1. Treat all information through 2026-08-20 as DEVELOPMENT; never use later outcomes for V18 selection.
2. Trace the corrected V10/V11 H12 replay from score generation to decision timestamps, optimizer, execution timing, costs/funding, fold reset and unwind.
3. Re-run only the fixed Ridge and fixed HistGB scores through that exact flow first.
4. If HistGB does not improve the corrected Ridge benchmark consistently in >=2 chronological development slices, reject nonlinear price-only rescue and do not run stacking/RL/HPO.
5. If HistGB does improve robustly, then and only then test the already-predeclared chronological stack once under corrected replay.
6. Keep the L2 recorder running for future untouched/paper validation; it no longer blocks research.
7. Optuna only if a scientifically justified future training run is expected to exceed one hour; current runs are ~2 minutes.
8. RL only after stable predictive edge exists, as a bounded simulation/paper policy layer with <=1x exposure.
9. Never consume trial 871 until all existing authorization gates pass.
