# Progress Log

## V16 checkpoint — 2026-08-24 Asia/Ho_Chi_Minh

- Read complete V15 directory and automation protocol before acting.
- Reconciled clean V11 worktree at starting SHA `2a4c027de3ee150ee6d8cf58c094dcfbf8cb8a43`.
- Recorder snapshot: L2 `RUNNING`, 4,701 cycles, 98,721 records, 0 errors; positioning `RUNNING`, 10 cycles, 1,260 rows, 0 errors.
- Local archive probe found no historical order-book/top-of-book dataset overlapping the old H12 panel; installed CCXT code/tests are libraries, not historical data.
- Official Binance public-data evidence shows bulk futures `bookTicker` stopped around March 2024 and the older historical futures L2 download route is no longer public bulk access, so neither covers the 2025–2026 H12 folds.
- Tardis has technically appropriate Binance USD-M depth/bookTicker history since 2019 with sequence-integrity validation, but free CSV access is sample-limited and full arbitrary-date history uses service/API access.
- Decision: do not pay/build a second historical pipeline merely to rescue H12. Close historical microstructure rescue and use the already-running first-seen local L2 recorder as a new forward-only research path.
- No strategy code/dependency changed, no prospective outcome inspected, no performance replay/trial consumed.
- Trial 871 remains unauthorized/unconsumed. `LIVE_NOT_AUTHORIZED`.
