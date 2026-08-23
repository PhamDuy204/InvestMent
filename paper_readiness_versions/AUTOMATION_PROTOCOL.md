# Hourly Automation Protocol

## Canonical paths

- Initial/current V11 worktree: `/home/duypham/workspace/InvestMent-v11-root-cause-paper-readiness`
- Version workspace: `/home/duypham/workspace/InvestMent-v11-root-cause-paper-readiness/paper_readiness_versions`
- Latest pointer: `/home/duypham/workspace/InvestMent-v11-root-cause-paper-readiness/paper_readiness_versions/LATEST`
- PC-local research data root: `/home/duypham/workspace/InvestMent-v9-local-data`
- GitHub: `PhamDuy204/InvestMent`

The worktree path may become stale after future research versions. Before work, discover actual `git worktree list`, branches, local/remote SHAs, and open PRs. Never blindly trust old paths/PIDs/SHAs.

## Each hourly run

1. Read `LATEST`, then read every file in that version directory before touching code.
2. Reconcile local/GitHub state and recorder health. Do not overwrite uncommitted work.
3. Pick the **single highest-leverage unresolved blocker** from `02_open_problems.md`.
4. Expand search only enough to answer the current question: repo code/helpers first, stdlib/installed dependencies second, primary literature/exchange docs/web last.
5. Split the blocker until one small falsifiable question remains. Prefer diagnosis over adding features.
6. Reuse existing replay/causal/test helpers. No new framework/dependency unless clearly necessary.
7. If code changes are needed: trace callers/shared flow, write one failing focused test for non-trivial logic, make the minimum fix, run focused tests, then full verification before claiming success.
8. Maintain strict evidence accounting: observed development data stays observed; untouched/prospective data is not inspected during design.
9. Do not consume the next performance trial unless all existing scientific authorization gates pass and the candidate/evaluation rule is frozen and predeclared.
10. Update the current version files with findings, evidence, questions answered, new questions, references, and remaining blockers.
11. Append a timestamped entry to `09_progress_log.md` every run.
12. Create `version_{N+1}` only when a meaningful checkpoint changed (resolved blocker, new root-cause evidence, selected defensible mechanism, authorized/finished trial, candidate freeze, readiness transition). Copy forward only still-relevant information and explicitly list what changed from N.
13. Commit/push meaningful changes as `duypham`, fetch, and verify local SHA == remote SHA. Check CI on the exact SHA. Do not merge automatically.
14. If and only if `READY_TO_START_PAPER=true` with an immutable candidate freeze, use the existing public-data + `SimulatedBroker`/`ExecutionSimulatorV8` paper path. Starting paper is not `PAPER_VALIDATED`.
15. Never perform live orders/cancellation, leverage/margin changes, borrowing, repayment, transfer, withdrawal, or other private trading API mutations. Always retain `LIVE_NOT_AUTHORIZED`.

## Stop conditions for a run

A run may legitimately end with `NO_MATERIAL_CHANGE`, `NEED_MORE_UNTOUCHED_EVIDENCE`, or a negative result. Do not manufacture a new mechanism/version just to show activity.
