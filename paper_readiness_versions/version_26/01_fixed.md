# Fixed Facts — V26

1. Raw H21-C standalone direction is rejected; no raw scale tuning is allowed.
2. H26 preserves H12 direction and target ceiling and can only block new/incremental exposure during sign conflict.
3. H26 has no fitted parameter; threshold = 0.0 by construction.
4. First test is corrected 10bps V11 evaluation partition only.
5. Fixed pass gate: aggregate candidate net return > 0 and > baseline; net improves in >=2/3 folds; aggregate wrong-side damage < baseline and improves in >=2/3 folds; turnover <= baseline.
6. If any gate fails, reject H26 before inventing nearby thresholds/scales.
7. Only if all gates pass may fixed 20bps and +1h stress be opened.
8. Trial 871 remains untouched.
