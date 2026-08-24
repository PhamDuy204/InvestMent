# Fixed Facts — V18

1. H12 is a trained 12-hour relative-return Ridge model (`StandardScaler -> Ridge(alpha=1.0)`).
2. Corrected V11 evidence showed H12 directional alpha fails before transaction costs; this historical evidence stays observed/development, not fresh OOS.
3. Data through 2026-08-20 may now be used for DEVELOPMENT/model research by explicit user instruction.
4. Data/outcomes after 2026-08-20 are not to be used for V18 model selection or HPO.
5. Official Binance USD-M hourly klines are available as daily/monthly public archives; funding history is available from the public funding-rate endpoint.
6. The V18 historical-development panel ends at 2026-08-20 23:00 UTC; last mature H12 decision is 2026-08-20 11:00 UTC.
7. Development validation must remain chronological with a 12-hour purge/gap for H12 labels.
8. Random K-fold stacking is prohibited. Meta-model training must use chronological OOF predictions only.
9. First fixed model ladder used exactly four configurations: Ridge, HistGB, ExtraTrees, and Ridge-meta stacking. No hyperparameter search was performed.
10. Naive stacking is not admitted as a superior V18 model from this diagnostic.
11. RL is not an alpha-discovery shortcut; consider it only after a predictive signal survives chronological development diagnostics.
12. Trial 871 remains untouched and all live mutations remain forbidden.
