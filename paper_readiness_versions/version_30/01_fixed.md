# Fixed Facts — V30

1. Forward L2 recorder schema/integrity is usable: 21/21 symbols, 0 checksum failures, no timestamp parse failures, stable same-day cadence.
2. The first feature remains the already-existing V17 `top_of_book_imbalance`; do not write a replacement feature layer just to continue research.
3. DEVELOPMENT cutoff remains `2026-08-20T23:59:59Z`. Only ~6.04 common 21-symbol hours exist before it.
4. Post-cutoff L2 is reserved; this run inspected only its metadata/schema/continuity, not returns or performance labels.
5. The 20→23 August recorder outage prevents treating all current L2 as a continuous forward window.
6. Six hours is insufficient for a defensible chronological H12 development test with independent slices. Do not manufacture folds from overlapping snapshots.
7. No new configuration/mechanism was tested; `DEVELOPMENT_CONFIGURATION_COUNT=10` remains unchanged.
8. Trial 871 remains unauthorized/unconsumed.
