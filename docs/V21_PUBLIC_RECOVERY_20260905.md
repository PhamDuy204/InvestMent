# V21 public stream and execution recovery — 2026-09-05

This revision preserves the paper schema, account, execution calibration, SQLite history, and public-data-only boundary. The monitoring objective is now $1 realized net PnL/hour over a long-run window; it is not an admission threshold or a promised return. No EV threshold or leverage limit was relaxed.

## Corrections

- CCXT 4.5.76 caches Classic KuCoin Futures URLs under `publicFutures`, while its token-expiry callback invalidates `public` and raises before rejecting watch futures. The local public-client subclass invalidates the matching namespace and passes the exception into the existing client lifecycle. A delayed callback from an old connection cannot invalidate a replacement token.
- Missing venue coverage now reports `DEGRADED`; an expired heartbeat still reports `STALE`. The 0–1 venue path writes the current state before health, so the dashboard cannot retain an earlier 7/7 count during an outage.
- Stream errors have a bounded rolling 60-second window alongside historical retry counters. The dashboard displays connected/expected venues and funding refresh age.
- A confirmed maker fill remains exposure when the hedge book disappears. It is unwound only against available executable depth, or remains `UNWIND_PENDING` with margin reserved. Missing data cannot erase the fill or turn it into a no-fill cancellation.
- One-leg aborts also back off the same symbol, maker venue and maker side for the existing 60-second period, preventing a hedge-venue change from bypassing that cooldown. Other maker legs remain eligible.

## Verification before deployment

- 532 backend tests passed, including public-token renewal concurrency, coverage/staleness precedence, outage-state publication, and four missing-hedge exposure cases (both maker sides, before and after entry timeout).
- 28 frontend tests passed; ESLint, TypeScript, production build, Python compile and whitespace checks passed. Two aiohttp deprecation warnings concern Python 3.13 cleanup behavior.
- An isolated live check used public KuCoin BTC and ETH books, injected the expiry callback into that isolated client, and received fresh books again after a second public token request. The old socket was removed. No runner state or account data was touched. This verifies recovery behavior, not a full natural 24-hour token-lifetime soak.
- Online SQLite backup and `quick_check=ok` were recorded before restart. Runtime verification is recorded separately in the deployment/soak artifact.

## Evidence and limitations

The pre-deployment account snapshot was $167.3552505653 equity from $100, with $67.3552505653 realized net PnL and approximately $0.55/hour over this run. One-leg aborts accounted for approximately -$44.95. These are historical model results across revisions, not a measured improvement from this patch or evidence of a real-money return.

Public order books cannot prove a real account's queue priority, order acknowledgement, cancel race, hedge latency, margin tier or liquidation outcome. Venue balances, precision/minimum sizes, contract multipliers, settlement evidence, rejected orders and partial fills must be validated before a real adapter could share the decision engine. Historical PnL has not been rewritten to invent evidence absent from the stored feed.

Additional funding/basis strategies must retain separate observation/calibration records. Projected funding is not realized PnL; positive quotes must survive entry/exit fees, depth, basis movement, asynchronous settlements and capital constraints before any promotion.

## Primary references

- [KuCoin Classic Futures public token](https://www.kucoin.com/docs-new/websocket-api/base-info/get-public-token-futures): public `bullet-public` negotiation needs no exchange credentials.
- [KuCoin Classic WebSocket lifecycle](https://www.kucoin.com/docs-new/websocket-api/base-info/introduction): tokens/connections have a finite lifetime.
- [OKX perpetual funding mechanism](https://www.okx.com/help/perps-funding-fee-mechanism): funding is charged at settlement for positions held then, with contract-specific intervals.
- [Bybit funding rate](https://www.bybit.com/en/help-center/article/Introduction-to-Funding-Rate): quoted funding changes before settlement.
