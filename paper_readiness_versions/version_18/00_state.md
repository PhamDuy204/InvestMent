# State — Version 18

V18 changes the research clock, not the paper-trading safety gate.

- Historical/model DEVELOPMENT may proceed immediately using only information available on or before **2026-08-20 23:59:59 UTC**.
- For H12 labels, the latest mature decision under that information cutoff is **2026-08-20 11:00 UTC**.
- Any market outcome after 2026-08-20 remains outside V18 development and is reserved for future untouched validation / paper-readiness evidence.
- The prior V17 seven-contiguous-day L2 rule is no longer a blocker for model research. It remains useful for forward L2 validation and paper evidence.
- V18 built a local historical-development panel from official Binance USD-M public data through 2026-08-20: 30 symbols, 693,360 hourly rows, 93,462 funding rows. No post-cutoff rows were read to build it.
- First V18 model-capacity diagnostic compared fixed Ridge, HistGradientBoosting, ExtraTrees, and leakage-safe chronological stacking on DEVELOPMENT only.
- Naive stacking did **not** show stable superiority: mean timestamp Spearman `-0.00488`, positive in `1/3` outer folds; Ridge `-0.01565` (`1/3`), HistGB `+0.00178` (`2/3`), ExtraTrees `+0.00074` (`1/3`).
- Top2-minus-bottom2 target spread was positive in `2/3` folds for stacking but very small (`5.43e-05`) and materially below Ridge (`0.001568`) and HistGB (`0.000786`).
- Economics emitted by the exploratory probe are **diagnostic only** and not promotion-eligible until reconciled with the corrected V11 execution/replay semantics.
- No Optuna or RL run is justified yet; the first model ladder run took about 110 seconds.
- Trial 871 remains unauthorized/unconsumed.
- `READY_TO_START_PAPER=false`; `A1=NOT_STARTED`; `PAPER_VALIDATED=false`.
- `LIVE_NOT_AUTHORIZED`.
