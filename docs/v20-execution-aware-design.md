# V20 Execution-Aware Paper Arbitrage Design

## Goal

Preserve V19's causal public-market-data execution and positive paired-close behavior while stopping account losses caused by one-leg maker fills that fail post-fill EV. Optimize account-level realized net PnL per elapsed hour, not win rate or trade count.

## Verified V19 root cause

At the 2026-08-30 15:30 UTC forensic snapshot, V19 reconciles exactly:

- 8 paired closes: +$0.660994 net.
- 33 one-leg aborts: -$8.427145 net.
- Account realized PnL: -$7.766150; equity: $92.233850.
- One-leg abort gross adverse move: -$5.514829; abort fees: $2.912316.
- 193 maker attempts: 152 no-fill cancels, 33 aborts, 8 paired opens.
- Empirical any-maker-fill probability: ~21%; paired-open probability: ~4%.
- Current maker_attempt_ev p_open is the probability that at least one maker fills. It is then used to credit the full paired capture, while a separate p_one * hedge_risk penalty models one-leg risk.
- Observed conditional abort loss is roughly 24.5 bps per filled-leg target notional, while modeled hedge_risk is only a few bps. Most maker fills are therefore valued as if they become viable paired positions even though most are rejected after the causal fill.
- No V19 terminal attempt had both maker legs fill (`both_maker_fill_count == 0`). All 8 paired opens were maker+taker hedges.

This is an attempt-EV model mismatch, not a failure of V19's causal post-fill revalidation. Post-fill rejection is preventing stale/negative pairs from opening, but the placement gate does not price the cost of those rejected fills.

## V20 architecture

### 1. Single-maker entry candidate

For every candidate route, evaluate two possible paper entry actions independently:

- maker LONG on the cheap venue, then taker SHORT hedge on the rich venue after a causal maker fill;
- maker SHORT on the rich venue, then taker LONG hedge on the cheap venue after a causal maker fill.

Only one maker leg is exposed for a pending entry. The action with the highest conservative account-level attempt EV may be selected. This removes the unmeasured dual-maker interaction and makes the risk surface side/venue-specific.

### 2. Shadow outcome calibration, no equity mutation

Reuse the existing causal maker probes. When a shadow maker probe fills on one side, use the same fresh public order-book snapshot to calculate:

- whether the opposite taker hedge has executable depth;
- the same post-fill EV decision used by paper execution;
- the immediate-unwind gross/fee/net bps if the post-fill decision rejects.

Store only evidence derived from public causal snapshots. Shadow records never modify equity, balances, realized PnL, or positions.

Maintain bounded SQLite aggregate evidence by maker venue + maker side, with a global fallback:

- fills observed;
- post-fill accepts;
- post-fill rejects;
- reject unwind net-bps samples/sums;
- accepted post-fill EV samples/sums.

Use conservative shrinkage: a lower-confidence accept probability and a conservative reject-loss estimate. Until evidence is sufficient, the real-paper action stays gated while shadow probes continue.

### 3. Account-level attempt EV

For a specific single-maker action:

`attempt_ev_bps = p_fill * (q_accept * conditional_pair_value_bps + (1 - q_accept) * reject_unwind_net_bps)`

where:

- `p_fill` is the existing causal conservative maker-fill probability for that venue/side;
- `q_accept` is the conservative post-fill accept probability learned from causal evidence;
- `conditional_pair_value_bps` is placement-time paired economics with maker entry on the selected side, taker entry on the hedge side, conservative taker exits, safety buffer, and adverse-selection allowance;
- `reject_unwind_net_bps` is negative and includes maker entry fee + taker unwind fee + adverse price movement from calibrated evidence.

The gate is allowed to reject more attempts. It must never turn a negative account-level EV action positive merely to increase trade frequency.

### 4. Causal execution after fill

After selected maker fill:

1. Recompute exact opposite taker VWAP from current executable depth.
2. Recompute current post-fill EV.
3. If tradeable: hedge immediately and create paired paper position.
4. Otherwise: unwind the filled maker leg immediately using current executable depth.
5. Journal exact maker side, fill-to-decision latency, fill-to-hedge/unwind latency, post-fill EV, abort gross, fees, and net.

### 5. Sizing/leverage

Keep 20x/30x/40x PAPER leverage only. Leverage is chosen from the *execution-aware account-dollar EV* and available executable depth, not the legacy placement EV alone.

The target notional is capped by:

- venue margin;
- gross leverage cap;
- executable opposite-hedge depth;
- executable immediate-unwind depth on the maker venue.

40x is permitted only when the selected action has the strongest conservative expected dollar profit and sufficient depth. Leverage never changes the sign of EV.

### 6. Throughput after leakage control

Do not add a large universe before the new attempt gate is working. First add event-aware scheduling over the existing 50-symbol public WS cache: prioritize symbols whose books changed since their last evaluation, while retaining a bounded fallback rotation for history sampling.

After fresh-paper telemetry shows non-paired loss is controlled, increase the symbol limit incrementally under the existing 1.2 GB/1.5 GB memory guards. Kraken Futures is an eligible research venue because current CCXT Pro supports public `watch_order_book` and its published base futures fee is 0.02% maker / 0.05% taker; it must still pass overlap/liquidity/WS-health scoring before being enabled in the production-paper universe.

### 7. Fee model

Use non-VIP/base fees only. Current official evidence supports:

- OKX 2 bps maker / 5 bps taker;
- Bybit 2 / 5.5;
- Bitget 2 / 6;
- KuCoin 2 / 6;
- Gate 2 / 5;
- MEXC API Futures 6 / 8;
- Kraken Futures 2 / 5.

Binance remains conservative until an exact current official base USD-M maker/taker table is independently verified. Do not infer a VIP/BNB discount.

### 8. Monitoring

Rename `Win Rate` to `Paired Win Rate` and expose separately:

- account realized PnL and PnL/hour;
- paired realized PnL and PnL/hour;
- non-paired execution PnL and PnL/hour;
- abort count/gross/fees/net;
- one-leg fill/post-fill reject/hedge counts;
- total/paired/non-paired fee drag;
- paired trades/hour;
- rolling 1h/3h/6h account PnL;
- median/p95 entry gap;
- maker-side calibration sample count, conservative accept probability, and reject-loss estimate.

## Validation

A V20 smoke run uses a separate artifacts directory and must not stop V19 runner/publisher/web/tunnel. Unit and integration checks are required before that run. No profitability claim is made from a short smoke. The target is only accepted from account-level realized PnL after sufficient elapsed windows, with 1h/3h/6h reported and longer windows when available.
