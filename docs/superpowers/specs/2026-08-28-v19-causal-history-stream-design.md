# V19 Causal History and Stream Design

## Goal

Build a paper-only V19 that removes V18's history starvation and avoidable event-loop work, uses the available two-core/1.9 GB host conservatively, and preserves honest fee, execution, slippage, adverse-selection, and post-fill EV gates. The profitability benchmark is an evaluation target, not an admission rule.

## Safety boundary

- Public market data only.
- Paper/simulation only.
- No credentials, authenticated exchange endpoints, create_order, place_order, withdraw, transfer, or deposit.
- Never fabricate orders, fills, PnL, execution, profitability, or WebSocket events.
- Do not lower EV, fee, depth, post-fill, or adverse-selection gates to increase trade count.
- V18 artifacts and runner remain available until V19 passes promotion checks.

## Verified V18 causes

### History starvation

V18 evaluates two of 50 symbols per discovery cycle but inherits V17's one global last_history_sample_ms. The current interval is 5 seconds. When the global clock becomes due, only the current two-symbol batch records history; the following batches are suppressed until the same global clock is due again. The resulting per-symbol sample interval is commonly 100-140 seconds.

multi_horizon_route_features requires at least 12 samples in 60 minutes, a minimum baseline span, at least three samples in 15 minutes, and at least three samples in five minutes. In the audited V18 database, only about one route out of more than 1,100 was fully ready at representative snapshots. This is a data pipeline failure before EV evaluation.

V17 seed aging is not the sole cause. ACU and APT attempts occurred more than two hours after the current runner began and were supported by V18's own sparse history.

### Stream semantics and load

V18 deep-copies all 350 cached books and then copies them again for a cycle that discovers only two symbols. A synthetic 350-book snapshot measured about 125 ms median and 191 ms p90. The route-history query lacks a route-leading index; adding (symbol, buy_venue, sell_venue, observed_at_ms) reduced the benchmarked query median from about 482 microseconds to 34 microseconds.

The 500 ms receive-time skew guard compares last content-change times, not synchronized observations. Change-driven feeds such as OKX books5 do not publish a new snapshot when the top five levels do not change. V18 also merges age expiry, skew rejection, disconnects, and subscription errors into aggregate fresh/stale and reconnect counters, preventing an exact forensic breakdown.

The installed CCXT Pro Gate adapter can delete an order-book subscription after a sequence gap while an already-arriving delta still enters handle_order_book. That delta reads the deleted key and raises KeyError. V18 retries, but does not preserve the venue/symbol/error classification.

### Execution evidence

APT's actual post-fill calculation is internally consistent:

2.7432 capture - 11 entry fees - 11 conservative exit fees - 0.5920 adverse selection - 0.5 safety = -20.3488 bps.

The one-leg abort PnL also reconciles to gross PnL less entry and exit fees. However, V18's maker fill is a paper assumption inferred from a later order-book touch/cross. A touch alone does not prove a trade or queue fill.

## Chosen approach

Combine per-symbol causal sampling with a larger but bounded discovery batch after removing the known allocation and query bottlenecks. Do not perform a heavy all-symbol decision pass every five seconds.

### History

- Replace the global history gate with a persisted per-symbol timestamp map.
- Record a symbol when that symbol is evaluated and its own interval is due.
- Keep the 5-second configured sampling interval.
- Keep at least 12 samples and the five-/15-/60-minute density checks.
- Reduce only the minimum history span from 10 minutes to 7 minutes.
- Keep the 60-minute structural median and 15-/5-minute local medians.
- Seed V19 route history once from V18 without copying account, trades, fill calibration, or PnL state.
- Add the route-leading SQLite index.

The seven-minute choice is based on archived public history rather than the profit target. At the latest comparable endpoints in V17, 57 routes had enough seven-minute data to compare with their ten-minute medians versus eight routes at five minutes. The median absolute seven-to-ten-minute baseline difference was about 0.0024 bps. Five minutes would also require lowering the 12-sample gate, so it is not selected.

### Resource use

- Materialize decision books only for the discovery batch plus symbols with pending entries, pending exits, probes, or open positions.
- Compute full-cache telemetry from immutable references/metadata rather than deep-copying all depth arrays.
- Reuse the existing cache/client pattern; add no dependency or worker pool.
- Raise the default discovery batch from two to five only after the selective snapshot and SQLite index are in place.
- Retain CLI control of batch size for rollback/tuning.
- On the current 1.9 GiB host, start with a 1,200 MB high-water mark and a 1,500 MB hard stop so the dashboard, publisher, operating system, and runner retain headroom. Expose CLI limits up to 3,000 MB for a future larger host; never allocate that limit when physical RAM is insufficient, and do not count swap as safe working memory. Never run a second full 350-stream runner concurrently.
- If the five-symbol batch violates the envelope in smoke/live observation, revert the CLI batch to two; do not weaken economic gates.

### Freshness and connection health

- Track connection/task health independently from content age.
- Preserve local wall and monotonic receive timestamps.
- Remove receive-time cross-venue skew from route admission because it is not a synchronized snapshot clock.
- Keep a bounded content-idle age, initially five seconds, and reject a book immediately when its stream task has a recorded disconnect/error.
- A causal maker fill still requires a strictly post-placement update. A book accepted for route evaluation is not automatically post-placement fill evidence.
- Record per-venue and per-symbol update, age-expiry, disconnect, reconnect, and normalized exception-reason counters.
- Treat the Gate subscription KeyError as an upstream adapter failure: preserve evidence, retry with bounded backoff, and do not monkey-patch CCXT or disable sequence validation.

### Candidate funnel

Keep qualified_opportunity_count for backward compatibility but add counters that distinguish:

- observed route occurrence;
- feature-ready occurrence;
- EV-qualified occurrence;
- unique candidate;
- duplicate/pending-route rejection;
- cooldown rejection;
- capacity/margin rejection;
- pending entry created;
- no causal fill;
- post-fill reject;
- paired open.

No metric may imply these are unique trades unless uniqueness is enforced.

### Maker fill and accounting

- Keep the causal post-placement timestamp requirement.
- Change paper maker evidence from touch-or-cross to strict price-through; a price equal to the limit is not sufficient.
- Label the result as a modeled paper fill, not an exchange fill.
- Do not use the new V18 AEVO/ATH wins as calibration proof.
- Preserve post-fill recomputation from actual modeled maker/taker prices.
- Preserve taker depth simulation, all entry/exit fees, conservative exit cost, adverse selection, and safety buffer.
- Keep one-leg aborts outside paired closed-trade counts while retaining their realized equity and fee effects.

## Versioning and files

Follow the repository's versioned runner pattern while reusing existing helpers:

- add scripts/run_arbitrage_paper_v19.py;
- add only small V19-specific modules where behavior cannot safely be shared;
- fix shared history/index logic once in its existing module;
- extend monitoring/publisher allow-lists for V19;
- add focused V19 regression tests;
- create artifacts/arbitrage_v19 only at runtime.

V18 behavior and artifacts must remain reproducible.

## Test strategy

Tests must fail on V18 behavior before implementation:

1. A 50-symbol/five-symbol rotating simulation gives every symbol independent history samples and makes stable routes feature-ready after seven minutes.
2. One symbol sampling does not suppress another symbol inside the global interval.
3. SQLite query plan uses the route-leading index.
4. A selected-symbol snapshot copies only selected/active books while full telemetry still counts the complete cache.
5. Connection errors, age expiry, and other rejection causes are separate.
6. Cross-venue last-change skew alone does not reject healthy bounded-age books.
7. Maker touch is not a fill; strict post-placement price-through is.
8. APT post-fill EV and one-leg abort accounting remain unchanged.
9. Candidate funnel counters reconcile from observation to pending/open.
10. No client path exposes or calls a private order method.

Run focused tests first, then the full backend suite, Ruff, compileall, git diff --check, frontend tests, frontend lint, and production build.

## Promotion and rollback

1. Keep V18 live during code/test work.
2. Do not run V18 and V19 full 350-stream production processes concurrently.
3. After all static/unit checks pass, stop V18 gracefully and start V19 with 50 symbols, batch five, new artifacts, and a one-time V18 history seed.
4. Observe health, memory, loop latency, per-symbol sampling density, feature readiness, stream failure causes, and journal invariants.
5. Switch the existing publisher to V19 only after state and health are valid.
6. Roll back to the preserved V18 command if memory, stream quality, invariants, or artifact publication fail.

Promotion proves engineering correctness and observability, not profitability. The $0.50/hour benchmark requires a materially larger post-cost paper sample.
