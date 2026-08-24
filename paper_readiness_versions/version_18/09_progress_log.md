# Progress Log

## V18 boundary/model checkpoint — 2026-08-24 Asia/Ho_Chi_Minh

- User explicitly separated model research from paper-trading waiting: development may use historical information through 2026-08-20; forward waiting is reserved for validation/paper evidence.
- Verified H12 is a trained 12h Ridge relative-return model and the repo already contains fixed HistGB/ExtraTrees implementations.
- Verified Binance official public-data support for historical USD-M hourly klines and public funding-rate history; no private/trading endpoint was used.
- Alpaca was explicitly invoked but its connector call was forbidden in this conversation. It was not substituted as a training source because its crypto feed is not the Binance USD-M perpetual market used by this project.
- Reused the existing historical cache and downloaded only official public Binance data for 2026-08-01 through 2026-08-20. Built a PC-local V18 panel with 693,360 hourly rows over 30 symbols and 93,462 funding rows; max raw timestamp 2026-08-20 23:00 UTC; latest mature H12 decision 2026-08-20 11:00 UTC; no post-cutoff row was read into the panel.
- First fixed model ladder (DEVELOPMENT only): Ridge, HistGradientBoosting, ExtraTrees, chronological OOF Ridge-meta stacking. Runtime ~110s, so Optuna/HPO is not justified.
- Mean timestamp Spearman by model: Ridge `-0.01565` (1/3 positive folds), HistGB `+0.00178` (2/3), ExtraTrees `+0.00074` (1/3), stack `-0.00488` (1/3). Naive stacking is not stably superior.
- Mean top2-minus-bottom2 H12 target spread: Ridge `0.001568`, HistGB `0.000786`, ExtraTrees `0.000935`, stack `0.0000543`; stack is not promoted.
- Exploratory economics from this probe are quarantined as diagnostic because they do not reproduce corrected V11 H12 replay semantics. Next work is exact replay reconciliation, not more model complexity.
- V17 seven-day L2 accumulation remains useful for untouched validation/paper evidence but no longer blocks model research.
- No Optuna, no RL, no trial 871, no paper start, no live mutation. `LIVE_NOT_AUTHORIZED`.
