# V14 Multi-Asset Leveraged Paper Arbitrage Design

## Goal

Upgrade V13 paper-only cross-exchange perpetual arbitrage into V14-B: a ranked multi-symbol portfolio with an explicit isolated-margin paper model, portfolio/venue caps, and opportunity diagnostics. V14-C cross-margin optimization is gated on V14-B evidence and is not activated automatically.

## Safety boundary

- PAPER / SIMULATION ONLY.
- Public CCXT market metadata and order books only.
- No exchange API keys, private endpoints, create_order, deposits, or live execution.
- Dashboard remains PUBLIC · READ ONLY and cannot influence runner decisions.

## V14-B model

- Universe: active linear USDT perpetuals listed on at least two successfully discovered public venues.
- Candidate selection: fetch executable books once per symbol, close existing positions first, then rank qualified new opportunities by net executable edge.
- Portfolio: at most 4 distinct open symbols.
- Canonical virtual equity continues from V13.
- Margin model: `ISOLATED_PAPER_V1`.
- Default exchange leverage: 2x.
- Portfolio gross exposure cap: 2.0x equity.
- Single-pair gross cap: 0.5x equity; two equal-quantity legs therefore target ~0.25x equity notional per leg at current equity.
- Venue collateral: initial paper equity split equally across venues whose market discovery succeeds. Margin is reserved per leg as `leg_notional / exchange_leverage`.
- Available venue margin = venue balance - initial margin reserved by that venue's open legs.
- Realized leg PnL and fees accrue back to the corresponding venue balance when the pair closes.
- No maintenance-margin or liquidation simulation in B until venue-specific maintenance tiers are modeled. Those fields remain unavailable rather than fabricated.

## Opportunity diagnostics

Each scan persists a bounded radar row per symbol with available venues, best positive executable edge after fees/safety, qualification status, and a rejection reason such as `INSUFFICIENT_VENUES`, `NO_POSITIVE_EDGE`, `EDGE_BELOW_MIN`, `DUPLICATE_SYMBOL`, `MAX_POSITIONS`, `GROSS_CAP`, or `VENUE_MARGIN`.

## Monitoring

V14 telemetry shows actual modeled leverage/margin even with zero open positions: margin model, configured leverage, gross leverage used/cap, total initial margin used, venue balances/margin/headroom, universe size, and opportunity radar. The existing $20/$50/$100 what-if panel remains simulation-only and is always visible; close-now PnL projections are only shown when a LIVE open mark exists.

## V14-C promotion gate

C is eligible only after B records at least 30 closed trades, at least 5 distinct traded symbols, at least 24 hours runtime, zero accounting/margin invariant failures, zero forced/invalid closes caused by missing model state, and stable telemetry. C will then replace fixed caps with a cost/risk-aware cross-margin portfolio optimizer using the existing `multi_asset_v3` and `leverage_v3` primitives, with maintenance margin/funding added from venue rules before activation.
