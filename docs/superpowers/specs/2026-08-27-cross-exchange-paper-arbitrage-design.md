# Cross-Exchange Paper Arbitrage Design

## Goal

Add a simulated-only cross-exchange perpetual-futures arbitrage runner that uses public order books from Binance, OKX, and MEXC, starts with exactly 20 USD of virtual equity, and never places live orders.

## Scope

V1 is crypto perpetual futures only. Equities are deliberately excluded because the available retail equity feed is venue-specific and can be sparse outside regular hours; adding equity market routing would be a separate subsystem.

The runner observes common USDT-settled perpetual markets on Binance, OKX, and MEXC through the already-installed `ccxt` dependency. It compares executable buy/sell prices across venues, walks real observed order-book depth with the existing `ExecutionSimulatorV8`, subtracts explicit taker fees and a configurable safety buffer, and records only simulated opportunities and trades.

## Safety boundary

- No API key, secret, account balance, or authenticated endpoint is required.
- No `create_order`, `create_orders`, or equivalent exchange write method exists in the V1 path.
- The exchange clients are public-data clients only.
- Initial paper equity defaults to 20.0 USD.
- Any unsupported, stale, crossed, empty, or partially executable book is rejected.
- A trade is accepted only when both legs can be fully simulated and expected net edge exceeds the configured threshold.

## Architecture

`arbitrage_v12.py` is pure decision logic. It accepts normalized books and fee assumptions, reuses `ExecutionSimulatorV8` for depth-aware fills, and returns immutable opportunity records.

`run_arbitrage_paper_v12.py` owns network I/O. It creates three public CCXT swap clients, discovers common USDT linear perpetual symbols, fetches books sequentially, feeds them into the pure scanner, and appends JSONL/JSON artifacts. It never imports or calls a private trading API.

The runner is restartable: the equity file is read at startup, every accepted simulated trade is appended to JSONL, and state updates are written atomically. A single pass is supported for smoke tests; loop mode sleeps between scans.

## Opportunity model

For each symbol and ordered venue pair:

1. Simulate buying `target_notional` on the candidate cheap venue.
2. Simulate selling the same `target_notional` on the candidate expensive venue.
3. Require both legs to fill the full requested notional from observed depth.
4. Compute gross convergence edge from the two simulated VWAPs.
5. Subtract both exchange taker fees and the configured safety buffer.
6. Accept only if net edge in basis points is at least `min_net_edge_bps`.

The default target notional is deliberately small relative to virtual equity. V1 does not model leverage, liquidation, transfer latency, maker queues, or actual fill races. Those are explicit ceilings of the experiment, not hidden assumptions.

## Persistence

Artifacts live under `artifacts/arbitrage_v12/` by default:

- `opportunities.jsonl`: every accepted simulated opportunity.
- `state.json`: current virtual equity, scan count, accepted trade count, and cumulative simulated PnL.
- `health.json`: last successful scan time and last error, if any.

V1 marks PnL as *paper edge capture*: accepted trade edge is applied to target notional immediately. This is useful for measuring opportunity quality but is not a claim that real two-leg execution would realize that edge.

## Testing

A small unit test file must prove:

- spread below total costs is rejected;
- profitable spread is accepted;
- insufficient depth is rejected rather than extrapolated;
- best opportunity is selected from multiple venues;
- a crossed/invalid book cannot become an accepted trade.

CI already runs `pytest`, `ruff`, and `compileall` on pushes, so no new test framework or dependency is added.

## Success criteria

The branch is ready for a local paper experiment when all tests pass and a one-shot public-data run can write a healthy state without credentials. Live trading remains out of scope.
