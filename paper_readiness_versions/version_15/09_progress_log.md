# Progress Log

## V15 checkpoint — 2026-08-24 04:50 +07

- Read complete V14 directory and automation protocol before acting.
- Reconciled current V11 worktree: clean `v11-root-cause-paper-readiness`, starting local SHA `76892720323cb0b881befca554d57d46c29e51e5`; public remote branch and PR #8 head matched that SHA.
- Previous SHA CI is fully green: both `push` and `pull_request` V5 CI runs completed `success`.
- Recorder snapshot: L2 `RUNNING`, 4,232 cycles, 88,872 records, 0 errors; positioning `RUNNING`, 9 cycles, 1,134 rows, 0 errors.
- Audited official Binance USD-M `bookDepth` on 4 symbols × 4 representative dates against independently checksum-verified 1m mark-price archives.
- Initial parser treated 2026 decimal `percentage` strings/±0.20% buckets as invalid; raw-row inspection showed a schema expansion, not corruption. Final fixed audit permits extra buckets while requiring ±1..±5 everywhere.
- Final audit: 16/16 objects available/checksum-valid; 12/16 pass fixed integrity gate. All four symbols on 2025-04-16 fail side/implied-price consistency: BTC side 94.95%, ETH 95.12%, SOL 80.97%, AAVE 91.44%. SOL within-bucket consistency is only 68.21%; AAVE 90.36%.
- 2025-09-20 and the audited 2026 dates are broadly consistent, including the new ±0.20% buckets, but cross-fold use requires the earliest fold too.
- Verdict: `REJECT_BOOKDEPTH_AS_CROSS_FOLD_DEVELOPMENT_SOURCE`. No symbol/date repair or Apr-2025 exclusion is permitted after observing the defect.
- No strategy code/dependency changed, no prospective outcome inspected, no performance replay/trial consumed.
- Trial 871 remains unauthorized/unconsumed. `LIVE_NOT_AUTHORIZED`.
