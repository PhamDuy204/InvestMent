import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEquitySeries,
  buildMarkedEquitySeries,
  getDisplayStatus,
  LIVE_POLL_MS,
  projectPositionScenario,
  projectOpportunityScenario,
  projectPortfolioCapacity,
  sanitizeTelemetry,
  validateTelemetry,
} from "../lib/telemetry.ts";
import { isAuthorized, isAuthorizedDigest } from "../lib/server-telemetry.ts";

const sample = {
  schema_version: "v13-monitoring-1",
  updated_at_utc: "2026-08-27T09:30:00+00:00",
  runner_health: "HEALTHY",
  runner_error: null,
  initial_equity: 20,
  equity: 20.2,
  realized_pnl: 0.2,
  return_pct: 1,
  scan_count: 100,
  opened_position_count: 2,
  closed_position_count: 2,
  open_position_count: 0,
  open_positions: [],
  closed_positions: [
    { position_id: "p1", closed_at: "2026-08-27T09:10:00+00:00", realized_net_pnl: 0.5 },
    { position_id: "p2", closed_at: "2026-08-27T09:20:00+00:00", realized_net_pnl: -0.3 },
  ],
  metrics: {
    win_rate_pct: 50,
    profit_factor: 1.66,
    avg_win: 0.5,
    avg_loss: -0.3,
    fee_drag: 0.1,
    avg_holding_seconds: 120,
    max_drawdown_pct: 1.46,
    opportunity_to_trade_pct: null,
    closed_trade_count: 2,
  },
};

test("display status handles waiting, stale, degraded, and healthy", () => {
  assert.equal(getDisplayStatus(null, Date.parse("2026-08-27T09:31:00Z")), "WAITING");
  assert.equal(getDisplayStatus(sample, Date.parse("2026-08-27T09:31:00Z")), "HEALTHY");
  assert.equal(getDisplayStatus(sample, Date.parse("2026-08-27T09:33:01Z")), "STALE");
  assert.equal(
    getDisplayStatus({ ...sample, runner_health: "DEGRADED" }, Date.parse("2026-08-27T09:31:00Z")),
    "DEGRADED",
  );
  assert.equal(
    getDisplayStatus({ ...sample, runner_health: "STALE" }, Date.parse("2026-08-27T09:31:00Z")),
    "STALE",
  );
});

test("equity series starts at initial equity and applies closes causally", () => {
  assert.deepEqual(buildEquitySeries(sample), [
    { label: "Start", equity: 20, pnl: 0 },
    { label: "09:10", equity: 20.5, pnl: 0.5 },
    { label: "09:20", equity: 20.2, pnl: 0.2 },
  ]);
});

test("stale data takes precedence over degraded runner health", () => {
  assert.equal(getDisplayStatus({ ...sample, runner_health: "DEGRADED" },
    Date.parse("2026-08-27T09:33:01Z")), "STALE");
});

test("bearer token comparison rejects wrong or missing tokens", () => {
  assert.equal(isAuthorized(null, "secret-token"), false);
  assert.equal(isAuthorized("Bearer wrong", "secret-token"), false);
  assert.equal(isAuthorized("Bearer secret-token", "secret-token"), true);
});

test("telemetry validation accepts schema and rejects malformed payload", () => {
  assert.equal(validateTelemetry(sample).ok, true);
  assert.equal(validateTelemetry({ ...sample, schema_version: "wrong" }).ok, false);
  assert.equal(validateTelemetry({ ...sample, equity: "20" }).ok, false);
  assert.equal(validateTelemetry({ ...sample, open_positions: {} }).ok, false);
});


test("server sanitizer drops unexpected top-level and position fields", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    secret: "never-store",
    closed_positions: [{ ...sample.closed_positions[0], apiKey: "never-store" }],
  });
  assert.ok(sanitized);
  assert.equal("secret" in sanitized, false);
  assert.equal("apiKey" in sanitized.closed_positions[0], false);
});


test("server sanitizer preserves allow-listed live mark fields", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    open_position_count: 1,
    open_positions: [{
      position_id: "open-1",
      symbol: "BNB/USDT:USDT",
      long_exchange: "okx",
      short_exchange: "mexc",
      quantity: 0.01,
      mark_status: "LIVE",
      long_current_vwap: 712.1,
      short_current_vwap: 713.4,
      estimated_net_pnl_if_closed: 0.0123,
      entry_gross_exposure: 9.98,
      exposure_pct_of_equity: 49.9,
      margin_model: "NOT_MODELED",
      secret: "drop-me",
    }],
  });
  assert.ok(sanitized);
  const position = sanitized.open_positions[0];
  assert.equal(position.mark_status, "LIVE");
  assert.equal(position.estimated_net_pnl_if_closed, 0.0123);
  assert.equal(position.margin_model, "NOT_MODELED");
  assert.equal("secret" in position, false);
});


test("sha256 bearer verification accepts only the matching token", () => {
  const digest = "4c5dc9b7708905f77f5e5d16316b5dfb425e68cb326dcd55a860e90a7707031e";
  assert.equal(isAuthorizedDigest(null, digest), false);
  assert.equal(isAuthorizedDigest("Bearer wrong", digest), false);
  assert.equal(isAuthorizedDigest("Bearer test-token", digest), true);
});


test("what-if scenario scales relative to the actual position leverage instead of double-counting it", () => {
  const position = {
    long_entry_notional: 4,
    short_entry_notional: 6,
    estimated_net_pnl_if_closed: -0.02,
    mark_status: "LIVE",
    leverage: 2,
  };

  const same = projectPositionScenario(position, 20, 20, 2);
  assert.equal(same.scale, 1);
  assert.equal(same.gross_exposure, 10);
  assert.equal(same.estimated_net_pnl_if_closed, -0.02);

  const scenario = projectPositionScenario(position, 20, 50, 5);
  assert.deepEqual(scenario, {
    scale: 6.25,
    actual_leverage: 2,
    scenario_leverage: 5,
    long_notional: 25,
    short_notional: 37.5,
    gross_exposure: 62.5,
    long_initial_margin: 5,
    short_initial_margin: 7.5,
    initial_margin: 12.5,
    margin_pct_of_capital: 25,
    estimated_net_pnl_if_closed: -0.125,
    pnl_pct_of_capital: -0.25,
    projected_account_value: 49.875,
  });
});

test("flat what-if turns a tradeable radar row into a visible hypothetical pair order", () => {
  assert.deepEqual(
    projectOpportunityScenario(
      { symbol: "BNB/USDT:USDT", buy_venue: "okx", sell_venue: "mexc", best_net_edge_bps: 8, signal_status: "TRADEABLE" },
      20,
      3,
      6,
    ),
    {
      symbol: "BNB/USDT:USDT",
      long_exchange: "okx",
      short_exchange: "mexc",
      leverage: 3,
      long_notional: 5,
      short_notional: 5,
      gross_exposure: 10,
      initial_margin: 10 / 3,
      best_net_edge_bps: 8,
    },
  );
});

test("dashboard realtime poll cadence is two seconds", () => {
  assert.equal(LIVE_POLL_MS, 2000);
});



test("V14 sanitizer preserves modeled portfolio risk and drops unknown radar fields", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v14-monitoring-1",
    margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "CROSS_MARGIN_OPTIMIZER_V1",
    maintenance_stress_rate: 0.05,
    margin_utilization_cap: 0.8,
    venue_concentration_penalty_bps: 2,
    maintenance_stress_used: 0.5,
    min_stress_margin_ratio: 39.6,
    exchange_leverage: 2,
    gross_leverage_cap: 2,
    gross_leverage_used: 0.5,
    gross_exposure: 10,
    initial_margin_used: 5,
    available_margin: 15,
    max_open_positions: 4,
    single_pair_gross_fraction: 0.5,
    qualified_opportunity_count: 7,
    observed_signal_count: 19,
    last_cycle_signal_count: 4,
    last_cycle_tradeable_count: 1,
    venue_balances: { okx: 10, mexc: 10 },
    venue_margin_used: { okx: 2.5, mexc: 2.5 },
    venue_available_margin: { okx: 5.5, mexc: 5.5 },
    venue_account_equity: { okx: 10.1, mexc: 9.9 },
    venue_unrealized_pnl: { okx: 0.1, mexc: -0.1 },
    venue_maintenance_stress: { okx: 0.25, mexc: 0.25 },
    venue_margin_ratio: { okx: 40.4, mexc: 39.6 },
    venue_margin_utilization: { okx: 0.2475, mexc: 0.2525 },
    universe_size: 30,
    invariant_failure_count: 0,
    started_at_utc: "2026-08-27T12:00:00+00:00",
    opportunity_radar: [{
      symbol: "BTC/USDT:USDT",
      available_venues: ["okx", "mexc"],
      venue_count: 2,
      decision: "EDGE_BELOW_MIN",
      buy_venue: "okx",
      sell_venue: "mexc",
      gross_edge_bps: 40,
      total_fee_bps: 26,
      safety_buffer_bps: 5,
      best_net_edge_bps: 9,
      signal_status: "TRADEABLE",
      edge_to_trade_bps: 0,
      optimizer_score_bps: 8.5,
      optimizer_rank: 1,
      secret: "drop-me",
    }],
    secret: "drop-me",
  });

  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v14-monitoring-1");
  assert.equal(sanitized.margin_model, "CROSS_MARGIN_PAPER_V1");
  assert.equal(sanitized.portfolio_model, "CROSS_MARGIN_OPTIMIZER_V1");
  assert.equal(sanitized.maintenance_stress_rate, 0.05);
  assert.equal(sanitized.min_stress_margin_ratio, 39.6);
  assert.equal(sanitized.exchange_leverage, 2);
  assert.equal(sanitized.gross_leverage_used, 0.5);
  assert.equal(sanitized.observed_signal_count, 19);
  assert.equal(sanitized.last_cycle_signal_count, 4);
  assert.equal(sanitized.last_cycle_tradeable_count, 1);
  assert.deepEqual(sanitized.venue_available_margin, { okx: 5.5, mexc: 5.5 });
  assert.deepEqual(sanitized.venue_account_equity, { okx: 10.1, mexc: 9.9 });
  assert.equal(sanitized.opportunity_radar[0].decision, "EDGE_BELOW_MIN");
  assert.equal(sanitized.opportunity_radar[0].signal_status, "TRADEABLE");
  assert.equal(sanitized.opportunity_radar[0].edge_to_trade_bps, 0);
  assert.equal(sanitized.opportunity_radar[0].optimizer_score_bps, 8.5);
  assert.equal(sanitized.opportunity_radar[0].optimizer_rank, 1);
  assert.deepEqual(sanitized.opportunity_radar[0].available_venues, ["okx", "mexc"]);
  assert.equal("secret" in sanitized, false);
  assert.equal("secret" in sanitized.opportunity_radar[0], false);
});

test("portfolio capacity exists without an open position", () => {
  assert.deepEqual(projectPortfolioCapacity(20, 3, 4), {
    capital: 20,
    leverage: 3,
    max_positions: 4,
    gross_capacity: 60,
    pair_gross_capacity: 15,
    leg_notional_capacity: 7.5,
    total_initial_margin_capacity: 20,
    pair_initial_margin_capacity: 5,
  });
});

test("V15 sanitizer preserves shadow strategy evidence and radar diagnostics without widening the allow-list", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v15-monitoring-1",
    margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "CROSS_MARGIN_OPTIMIZER_V1",
    exchange_leverage: 2,
    gross_leverage_cap: 2,
    gross_leverage_used: 0.4,
    gross_exposure: 8,
    initial_margin_used: 4,
    available_margin: 12,
    max_open_positions: 6,
    single_pair_gross_fraction: 0.3,
    qualified_opportunity_count: 7,
    observed_signal_count: 19,
    last_cycle_signal_count: 4,
    last_cycle_tradeable_count: 1,
    universe_size: 50,
    invariant_failure_count: 0,
    shadow_updated_at_utc: "2026-08-27T13:00:00+00:00",
    strategy_lab: [
      { strategy_id: "CONTROL_V14C", mode: "CONTROL", realized_pnl: -0.04, open_position_count: 0, closed_trade_count: 3, secret: "drop" },
      { strategy_id: "ADAPTIVE_EXIT_SHADOW_V1", mode: "SHADOW", realized_pnl: 0.02, open_position_count: 1, closed_trade_count: 2, win_rate_pct: 50, profit_factor: 1.5, raw_positions: ["drop"] },
      { strategy_id: "SPREAD_CONTINUATION_SHADOW_V1", mode: "SHADOW", realized_pnl: -0.01, open_position_count: 0, closed_trade_count: 1, win_rate_pct: 0, profit_factor: null },
      { strategy_id: "FUNDING_AWARE_SHADOW_V1", mode: "OBSERVATION_ONLY", observed_route_count: 4 },
      { strategy_id: "INJECTED", mode: "SHADOW", realized_pnl: 999 },
    ],
    opportunity_radar: [{
      symbol: "AAA/USDT:USDT",
      available_venues: ["cheap", "rich"],
      venue_count: 2,
      buy_venue: "cheap",
      sell_venue: "rich",
      best_net_edge_bps: -3,
      signal_status: "WATCH",
      decision: "NO_POSITIVE_EDGE",
      persistence_sample_count: 7,
      persistence_seconds: 1800,
      spread_slope_bps_per_min: 0.2,
      funding_status: "AVAILABLE",
      funding_edge_bps: 1.25,
      secret: "drop",
    }],
    secret: "drop",
  });

  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v15-monitoring-1");
  assert.equal(sanitized.shadow_updated_at_utc, "2026-08-27T13:00:00+00:00");
  assert.deepEqual(sanitized.strategy_lab.map((row) => row.strategy_id), [
    "CONTROL_V14C",
    "ADAPTIVE_EXIT_SHADOW_V1",
    "SPREAD_CONTINUATION_SHADOW_V1",
    "FUNDING_AWARE_SHADOW_V1",
  ]);
  assert.equal(sanitized.strategy_lab[1].profit_factor, 1.5);
  assert.equal("secret" in sanitized.strategy_lab[0], false);
  assert.equal("raw_positions" in sanitized.strategy_lab[1], false);
  assert.equal(sanitized.opportunity_radar[0].persistence_seconds, 1800);
  assert.equal(sanitized.opportunity_radar[0].spread_slope_bps_per_min, 0.2);
  assert.equal(sanitized.opportunity_radar[0].funding_edge_bps, 1.25);
  assert.equal("secret" in sanitized.opportunity_radar[0], false);
  assert.equal("secret" in sanitized, false);
});

test("V16 sanitizer preserves route-relative diagnostics and bounded history", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v16-monitoring-1",
    initial_equity: 100,
    equity: 100,
    margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "ROUTE_RELATIVE_MULTI_STRATEGY_V1",
    exchange_leverage: 3,
    gross_leverage_cap: 2,
    gross_leverage_used: 0.2,
    gross_exposure: 20,
    initial_margin_used: 7,
    available_margin: 80,
    max_open_positions: 8,
    single_pair_gross_fraction: 0.2,
    qualified_opportunity_count: 2,
    observed_signal_count: 4,
    last_cycle_signal_count: 2,
    last_cycle_tradeable_count: 1,
    universe_size: 50,
    invariant_failure_count: 0,
    open_position_count: 1,
    open_positions: [{
      position_id: "p16",
      symbol: "BNB/USDT:USDT",
      strategy_id: "ROUTE_RELATIVE_MEAN_REVERSION_V1",
      entry_baseline_bps: 37,
      entry_excess_spread_bps: 35,
      entry_excess_after_cost_bps: 7,
      entry_fee_hurdle_bps: 28,
      entry_z_score: 3,
      entry_route_sigma_bps: 4,
      entry_short_slope_bps_per_min: -0.2,
      entry_price_volatility_bps: 12,
      pair_gross_fraction: 0.2,
      leverage: 3,
      secret: "drop",
    }],
    opportunity_radar: [{
      symbol: "BNB/USDT:USDT",
      available_venues: ["bitget", "mexc"],
      buy_venue: "bitget",
      sell_venue: "mexc",
      gross_edge_bps: 72,
      total_fee_bps: 28,
      safety_buffer_bps: 0.5,
      baseline_bps: 37,
      route_sigma_bps: 4,
      excess_spread_bps: 35,
      fee_hurdle_bps: 28.5,
      excess_after_cost_bps: 6.5,
      z_score: 8.75,
      short_slope_bps_per_min: -0.2,
      medium_slope_bps_per_min: 0.1,
      price_volatility_bps: 12,
      history_sample_count: 100,
      history_span_seconds: 3600,
      proposed_leverage: 3,
      proposed_pair_gross_fraction: 0.2,
      proposed_target_notional: 10,
      signal_status: "TRADEABLE",
      decision: "OPENED",
      raw: "drop",
    }],
    account_history: [{
      observed_at_ms: 1000,
      realized_equity: 100,
      marked_equity: 99.9,
      realized_pnl: 0,
      unrealized_net_pnl: -0.1,
      gross_exposure: 20,
      margin_used: 7,
      modeled_fee_drag: 0.03,
      secret: 999,
    }],
    position_history: {
      p16: [{ observed_at_ms: 1000, symbol: "BNB/USDT:USDT", spread_bps: 71, net_pnl: -0.1, baseline_bps: 37, raw: "drop" }],
    },
  });

  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v16-monitoring-1");
  assert.equal(sanitized.open_positions[0].entry_baseline_bps, 37);
  assert.equal(sanitized.open_positions[0].entry_z_score, 3);
  assert.equal(sanitized.opportunity_radar[0].excess_after_cost_bps, 6.5);
  assert.equal(sanitized.opportunity_radar[0].proposed_leverage, 3);
  assert.equal(sanitized.account_history[0].marked_equity, 99.9);
  assert.equal(sanitized.position_history.p16[0].baseline_bps, 37);
  assert.equal("secret" in sanitized.open_positions[0], false);
  assert.equal("raw" in sanitized.opportunity_radar[0], false);
  assert.equal("secret" in sanitized.account_history[0], false);
  assert.equal("raw" in sanitized.position_history.p16[0], false);
});

test("V16 marked equity series uses causal account snapshots", () => {
  const telemetry = sanitizeTelemetry({
    ...sample,
    schema_version: "v16-monitoring-1",
    initial_equity: 100,
    equity: 100.2,
    margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "ROUTE_RELATIVE_MULTI_STRATEGY_V1",
    exchange_leverage: 3,
    gross_leverage_cap: 2,
    gross_leverage_used: 0.2,
    gross_exposure: 20,
    initial_margin_used: 7,
    available_margin: 80,
    max_open_positions: 8,
    single_pair_gross_fraction: 0.2,
    qualified_opportunity_count: 1,
    observed_signal_count: 1,
    last_cycle_signal_count: 1,
    last_cycle_tradeable_count: 1,
    universe_size: 50,
    invariant_failure_count: 0,
    account_history: [
      { observed_at_ms: 1_000, realized_equity: 100, marked_equity: 99.9, realized_pnl: 0, unrealized_net_pnl: -0.1, gross_exposure: 20, margin_used: 7, modeled_fee_drag: 0.03 },
      { observed_at_ms: 61_000, realized_equity: 100.2, marked_equity: 100.35, realized_pnl: 0.2, unrealized_net_pnl: 0.15, gross_exposure: 15, margin_used: 5, modeled_fee_drag: 0.05 },
    ],
    position_history: {},
  });
  assert.ok(telemetry);
  assert.deepEqual(buildMarkedEquitySeries(telemetry), [
    { label: "00:00", equity: 99.9, pnl: -0.1 },
    { label: "00:01", equity: 100.35, pnl: 0.35 },
  ]);
});

test("V17 sanitizer preserves maker EV diagnostics, pending orders, and marked history", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v17-monitoring-1",
    initial_equity: 100,
    equity: 100,
    margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "MAKER_FIRST_EV_MULTI_STRATEGY_V1",
    exchange_leverage: 3,
    gross_leverage_cap: 2,
    gross_leverage_used: 0,
    gross_exposure: 0,
    initial_margin_used: 0,
    available_margin: 100,
    max_open_positions: 8,
    single_pair_gross_fraction: 0.2,
    qualified_opportunity_count: 1,
    observed_signal_count: 4,
    last_cycle_signal_count: 2,
    last_cycle_tradeable_count: 1,
    universe_size: 50,
    invariant_failure_count: 0,
    pending_entry_count: 1,
    pending_exit_count: 0,
    pending_entries: [{
      pending_id: "pe1", symbol: "AAA/USDT:USDT", long_exchange: "okx", short_exchange: "bybit",
      quantity: 0.1, placed_at_utc: "2026-08-28T03:00:00+00:00", status: "PENDING_MAKER_ENTRY",
      long_limit_price: 100, short_limit_price: 101, expected_value_bps: 2.2,
      minimum_required_ev_bps: 0.4, capture_bps: 15, p_open: 0.6, leverage: 2,
      position_key: "drop", apiKey: "drop",
    }],
    pending_exits: [],
    maker_probe_count: 12,
    maker_fill_observation_count: 20,
    maker_entry_cancel_count: 3,
    one_leg_hedge_count: 1,
    maker_exit_fallback_count: 0,
    maker_hedge_failure_count: 0,
    opportunity_radar: [{
      symbol: "AAA/USDT:USDT", available_venues: ["okx", "bybit"], buy_venue: "okx", sell_venue: "bybit",
      decision: "PASSIVE_TRADEABLE", signal_status: "TRADEABLE", gross_edge_bps: 20,
      baseline_60m_bps: 5, baseline_15m_bps: 4, baseline_5m_bps: 3,
      capture_bps: 15, expected_value_bps: 2.2, minimum_required_ev_bps: 0.4,
      p_open: 0.6, p_one_leg: 0.3, long_fill_probability: 0.7, short_fill_probability: 0.6,
      maker_round_trip_hurdle_bps: 8.5, four_taker_hurdle_bps: 21.5, long_quote_spread_bps: 3, short_quote_spread_bps: 4,
      expected_entry_price_improvement_bps: 4.5, expected_exit_price_improvement_bps: 4.2, secret: "drop",
    }],
    account_history: [{ observed_at_ms: 1_000, realized_equity: 100, marked_equity: 99.9, realized_pnl: 0,
      unrealized_net_pnl: -0.1, gross_exposure: 20, margin_used: 7, modeled_fee_drag: 0.03 }],
    position_history: {},
  });
  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v17-monitoring-1");
  assert.equal(sanitized.pending_entry_count, 1);
  assert.equal(sanitized.pending_entries[0].status, "PENDING_MAKER_ENTRY");
  assert.equal("position_key" in sanitized.pending_entries[0], false);
  assert.equal("apiKey" in sanitized.pending_entries[0], false);
  assert.equal(sanitized.opportunity_radar[0].expected_value_bps, 2.2);
  assert.equal(sanitized.opportunity_radar[0].p_open, 0.6);
  assert.equal(sanitized.opportunity_radar[0].maker_round_trip_hurdle_bps, 8.5);
  assert.equal(sanitized.opportunity_radar[0].long_quote_spread_bps, 3);
  assert.equal(sanitized.opportunity_radar[0].short_quote_spread_bps, 4);
  assert.equal(sanitized.opportunity_radar[0].expected_entry_price_improvement_bps, 4.5);
  assert.equal(sanitized.opportunity_radar[0].expected_exit_price_improvement_bps, 4.2);
  assert.equal("secret" in sanitized.opportunity_radar[0], false);
  assert.deepEqual(buildMarkedEquitySeries(sanitized), [{ label: "00:00", equity: 99.9, pnl: -0.1 }]);
});

test("V18 sanitizer preserves stream health and post-fill execution evidence", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v18-monitoring-1",
    initial_equity: 100, equity: 99.9, margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "WS_CAUSAL_POST_FILL_EV_V1", exchange_leverage: 40,
    gross_leverage_cap: 40, gross_leverage_used: 4, gross_exposure: 400,
    initial_margin_used: 10, available_margin: 90, max_open_positions: 8,
    single_pair_gross_fraction: 4, qualified_opportunity_count: 1,
    observed_signal_count: 3, last_cycle_signal_count: 2, last_cycle_tradeable_count: 1,
    universe_size: 50, invariant_failure_count: 0,
    pending_entry_count: 0, pending_exit_count: 0, pending_entries: [], pending_exits: [],
    maker_probe_count: 12, maker_fill_observation_count: 20, maker_entry_cancel_count: 3,
    one_leg_hedge_count: 1, maker_exit_fallback_count: 0, maker_hedge_failure_count: 0,
    post_fill_accept_count: 4, post_fill_reject_count: 3, both_maker_fill_count: 1,
    one_leg_abort_count: 3, one_leg_abort_pnl: -0.02, book_update_count: 12345,
    ws_reconnect_count: 2, book_cache_entry_count: 200, fresh_book_count: 190,
    stale_book_count: 10, connected_venue_count: 7, book_age_ms_median: 85,
    book_age_ms_max: 420, memory_prune_count: 6, process_rss_bytes: 734003200,
    open_position_count: 1,
    open_positions: [{
      position_id: "p18", actual_gross_spread_bps: 22, actual_capture_bps: 8,
      post_fill_expected_value_bps: 1.5, post_fill_decision: "POST_FILL_EV_ACCEPTED",
      apiKey: "drop",
    }],
    account_history: [{ observed_at_ms: 1_000, realized_equity: 100, marked_equity: 99.9,
      realized_pnl: -0.1, unrealized_net_pnl: 0, gross_exposure: 0, margin_used: 0,
      modeled_fee_drag: 0.02 }],
    position_history: {}, opportunity_radar: [],
  });

  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v18-monitoring-1");
  assert.equal(sanitized.book_update_count, 12345);
  assert.equal(sanitized.post_fill_reject_count, 3);
  assert.equal(sanitized.one_leg_abort_pnl, -0.02);
  assert.equal(sanitized.open_positions[0].actual_capture_bps, 8);
  assert.equal(sanitized.open_positions[0].post_fill_decision, "POST_FILL_EV_ACCEPTED");
  assert.equal("apiKey" in sanitized.open_positions[0], false);
  assert.deepEqual(buildMarkedEquitySeries(sanitized), [{ label: "00:00", equity: 99.9, pnl: -0.1 }]);
});


test("V17 tradeable maker-EV row can drive hypothetical sizing even when four-taker net is negative", () => {
  const projected = projectOpportunityScenario(
    {
      symbol: "AAA/USDT:USDT",
      buy_venue: "okx",
      sell_venue: "bybit",
      best_net_edge_bps: -8,
      expected_value_bps: 2.4,
      signal_status: "TRADEABLE",
    },
    100,
    2,
    8,
  );
  assert.ok(projected);
  assert.equal(projected.best_net_edge_bps, 2.4);
});


test("V19 sanitizer preserves bounded funnel and normalized stream causes", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v19-monitoring-1",
    initial_equity: 100, equity: 100, margin_model: "CROSS_MARGIN_PAPER_V1",
    portfolio_model: "WS_CAUSAL_POST_FILL_EV_V2", exchange_leverage: 40,
    gross_leverage_cap: 40, gross_leverage_used: 0, gross_exposure: 0,
    initial_margin_used: 0, available_margin: 100, max_open_positions: 8,
    single_pair_gross_fraction: 4, qualified_opportunity_count: 8,
    observed_signal_count: 10, last_cycle_signal_count: 2, last_cycle_tradeable_count: 1,
    universe_size: 50, invariant_failure_count: 0,
    pending_entry_count: 1, pending_exit_count: 0,
    pending_entries: [{
      pending_id: "unwind-1", symbol: "AAA/USDT:USDT", long_exchange: "okx", short_exchange: "bybit",
      quantity: 0.1, placed_at_utc: "2026-08-28T03:00:00+00:00", status: "UNWIND_PENDING",
      filled_side: "LONG", filled_venue: "okx", cancelled_maker_leg: "SHORT",
      unwind_reason: "HEDGE_DEPTH_UNAVAILABLE", unwind_pending_since_utc: "2026-08-28T03:00:01+00:00",
      partial_entry_price: 100, partial_entry_notional: 10, partial_entry_fee_bps: 2,
      partial_entry_fee: 0.002, partial_gross_notional: 9.99, partial_unrealized_pnl: -0.003,
      partial_initial_margin: 0.4995, partial_mark_status: "LIVE",
      unwind_attempt_count: 2, unwind_failure_count: 2,
      last_unwind_snapshot_at_ms: 123456, apiKey: "drop",
    }],
    pending_exits: [],
    maker_probe_count: 0, maker_fill_observation_count: 0, maker_entry_cancel_count: 0,
    one_leg_hedge_count: 0, maker_exit_fallback_count: 0, maker_hedge_failure_count: 0,
    post_fill_accept_count: 3, post_fill_reject_count: 1, both_maker_fill_count: 0,
    one_leg_abort_count: 1, one_leg_abort_pnl: -0.01,
    one_leg_unwind_attempt_count: 2, one_leg_unwind_failure_count: 2,
    partial_exposure_count: 1, partial_exposure_gross_notional: 9.99,
    partial_exposure_unrealized_pnl: -0.003, partial_exposure_entry_fees: 0.002,
    partial_exposure_reserved_margin: 0.4995, book_update_count: 100,
    ws_reconnect_count: 3, book_cache_entry_count: 25, fresh_book_count: 20,
    stale_book_count: 5, connected_venue_count: 7, book_age_ms_median: 80,
    book_age_ms_max: 400, memory_prune_count: 0, process_rss_bytes: 500000000,
    age_expired_book_count: 2, skew_rejected_book_count: 0, disconnected_book_count: 3,
    candidate_funnel_counts: {
      observed_route_occurrence: 10, feature_ready_occurrence: 9, ev_qualified_occurrence: 8,
      unique_candidate: 7, duplicate_rejected: 1, cooldown_rejected: 1,
      capacity_rejected: 1, margin_rejected: 1, depth_rejected: 1,
      reprice_ev_rejected: 1, pending_created: 1, no_causal_fill: 2,
      post_fill_rejected: 1, execution_abort: 2, paired_open: 3,
      "credential-like-secret": 999,
    },
    stream_error_counts: { KeyError: 2, RuntimeError: 1, "credential-like-secret": 50 },
    stream_error_counts_by_venue: {
      gate: { KeyError: 2, "credential-like-secret": 50 },
    },
    account_history: [], position_history: {}, opportunity_radar: [],
    raw_exchange_payload: { apiKey: "never-export" },
  });

  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v19-monitoring-1");
  assert.equal(sanitized.candidate_funnel_counts.pending_created, 1);
  assert.equal(sanitized.candidate_funnel_counts.execution_abort, 2);
  assert.equal("credential-like-secret" in sanitized.candidate_funnel_counts, false);
  assert.equal(sanitized.partial_exposure_count, 1);
  assert.equal(sanitized.partial_exposure_gross_notional, 9.99);
  assert.equal(sanitized.partial_exposure_reserved_margin, 0.4995);
  assert.equal(sanitized.one_leg_unwind_attempt_count, 2);
  assert.equal(sanitized.one_leg_unwind_failure_count, 2);
  assert.equal(sanitized.pending_entries[0].status, "UNWIND_PENDING");
  assert.equal(sanitized.pending_entries[0].unwind_reason, "HEDGE_DEPTH_UNAVAILABLE");
  assert.equal(sanitized.pending_entries[0].unwind_pending_since_utc, "2026-08-28T03:00:01+00:00");
  assert.equal(sanitized.pending_entries[0].partial_entry_fee, 0.002);
  assert.equal(sanitized.pending_entries[0].partial_unrealized_pnl, -0.003);
  assert.equal("last_unwind_snapshot_at_ms" in sanitized.pending_entries[0], false);
  assert.equal("apiKey" in sanitized.pending_entries[0], false);
  assert.equal(sanitized.age_expired_book_count, 2);
  assert.equal(sanitized.disconnected_book_count, 3);
  assert.deepEqual(sanitized.stream_error_counts, { KeyError: 2, RuntimeError: 1 });
  assert.deepEqual(sanitized.stream_error_counts_by_venue, { gate: { KeyError: 2 } });
  assert.equal(JSON.stringify(sanitized).includes("never-export"), false);
  for (const invalid of [
    { ...sanitized, age_expired_book_count: -1 },
    { ...sanitized, disconnected_book_count: 1.5 },
    {
      ...sanitized,
      candidate_funnel_counts: { ...sanitized.candidate_funnel_counts, no_causal_fill: -1 },
    },
    {
      ...sanitized,
      candidate_funnel_counts: { ...sanitized.candidate_funnel_counts, paired_open: 1.5 },
    },
  ]) {
    assert.equal(validateTelemetry(invalid).ok, false);
  }
});

test("V20 sanitizer preserves account-level execution truth metrics", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v20-monitoring-1",
    initial_equity: 100, equity: 100.1, realized_pnl: 0.1,
    margin_model: "CROSS_MARGIN_PAPER_V1", portfolio_model: "WS_EXECUTION_AWARE_SINGLE_MAKER_V1",
    exchange_leverage: 40, gross_leverage_cap: 40, gross_leverage_used: 0, gross_exposure: 0,
    initial_margin_used: 0, available_margin: 100, max_open_positions: 8, single_pair_gross_fraction: 4,
    qualified_opportunity_count: 8, observed_signal_count: 10, last_cycle_signal_count: 2,
    last_cycle_tradeable_count: 1, universe_size: 80, invariant_failure_count: 0,
    pending_entry_count: 0, pending_exit_count: 0, pending_entries: [], pending_exits: [],
    maker_probe_count: 2, maker_fill_observation_count: 3, maker_entry_cancel_count: 1,
    one_leg_hedge_count: 1, maker_exit_fallback_count: 0, maker_hedge_failure_count: 0,
    post_fill_accept_count: 2, post_fill_reject_count: 1, both_maker_fill_count: 0,
    one_leg_abort_count: 1, one_leg_abort_pnl: -0.2,
    one_leg_unwind_attempt_count: 1, one_leg_unwind_failure_count: 0,
    partial_exposure_count: 0, partial_exposure_gross_notional: 0,
    partial_exposure_unrealized_pnl: 0, partial_exposure_entry_fees: 0,
    partial_exposure_reserved_margin: 0, book_update_count: 100,
    ws_reconnect_count: 1, book_cache_entry_count: 30, fresh_book_count: 28,
    stale_book_count: 2, connected_venue_count: 8, book_age_ms_median: 75,
    book_age_ms_max: 300, memory_prune_count: 0, process_rss_bytes: 480000000,
    age_expired_book_count: 1, skew_rejected_book_count: 0, disconnected_book_count: 1,
    candidate_funnel_counts: {
      observed_route_occurrence: 10, feature_ready_occurrence: 9, ev_qualified_occurrence: 8,
      unique_candidate: 7, duplicate_rejected: 1, cooldown_rejected: 0, capacity_rejected: 0,
      margin_rejected: 0, depth_rejected: 0, reprice_ev_rejected: 0, pending_created: 2,
      no_causal_fill: 1, post_fill_rejected: 1, execution_abort: 1, paired_open: 1,
    },
    stream_error_counts: {}, stream_error_counts_by_venue: {}, account_history: [], position_history: {},
    opportunity_radar: [],
    paired_realized_pnl: 0.3, non_paired_execution_pnl: -0.2,
    account_pnl_reconciliation_error: 0, abort_count: 1, abort_gross_pnl: -0.15,
    abort_fees: 0.05, abort_net_pnl: -0.2, realized_funding_pnl: -0.01,
    funding_pnl_per_hour: -0.01 / 3, paired_fee_drag: 0.07,
    non_paired_fee_drag: 0.05, total_fee_drag: 0.12, runtime_hours: 3,
    paired_trades_per_hour: 2 / 3, paired_pnl_per_hour: 0.1,
    account_pnl_per_hour: 0.1 / 3, abort_count_per_hour: 1 / 3,
    abort_loss_per_hour: -0.2 / 3, rolling_1h_pnl: -0.2,
    rolling_3h_pnl: 0.1, rolling_6h_pnl: 0.1,
    median_entry_gap_seconds: 3600, p95_entry_gap_seconds: 3600,
  });
  assert.ok(sanitized);
  assert.equal(sanitized.schema_version, "v20-monitoring-1");
  assert.equal(sanitized.paired_realized_pnl, 0.3);
  assert.equal(sanitized.non_paired_execution_pnl, -0.2);
  assert.equal(sanitized.account_pnl_per_hour, 0.1 / 3);
  assert.equal(sanitized.abort_count, 1);
  assert.equal(sanitized.realized_funding_pnl, -0.01);
  assert.equal(sanitized.funding_pnl_per_hour, -0.01 / 3);
  assert.equal(sanitized.total_fee_drag, 0.12);
  assert.equal(sanitized.rolling_1h_pnl, -0.2);
  assert.equal(sanitized.p95_entry_gap_seconds, 3600);
});

test("V21 sanitizer preserves cohort execution radar evidence end to end", () => {
  const sanitized = sanitizeTelemetry({
    ...sample,
    schema_version: "v21-monitoring-1",
    initial_equity: 100, equity: 100, realized_pnl: 0, return_pct: 0,
    margin_model: "CROSS_MARGIN_PAPER_V1", portfolio_model: "WS_COHORT_CALIBRATED_SINGLE_MAKER_V2",
    exchange_leverage: 40, gross_leverage_cap: 40, gross_leverage_used: 0, gross_exposure: 0,
    initial_margin_used: 0, available_margin: 100, max_open_positions: 8, single_pair_gross_fraction: 4,
    qualified_opportunity_count: 0, observed_signal_count: 10, last_cycle_signal_count: 2,
    last_cycle_tradeable_count: 0, universe_size: 50, invariant_failure_count: 0,
    pending_entry_count: 0, pending_exit_count: 0, pending_entries: [], pending_exits: [],
    maker_probe_count: 2, maker_fill_observation_count: 0, maker_entry_cancel_count: 0,
    one_leg_hedge_count: 0, maker_exit_fallback_count: 0, maker_hedge_failure_count: 0,
    post_fill_accept_count: 0, post_fill_reject_count: 0, both_maker_fill_count: 0,
    v21_shadow_accept_count: 26, v21_shadow_reject_count: 518, public_trade_update_count: 4321,
    public_trade_update_counts_by_venue: { okx: 4000, gate: 321, secret: 99 },
    one_leg_abort_count: 0, one_leg_abort_pnl: 0, book_update_count: 100, ws_reconnect_count: 0,
    book_cache_entry_count: 50, fresh_book_count: 50, stale_book_count: 0, connected_venue_count: 7,
    memory_prune_count: 0, process_rss_bytes: 480000000, account_history: [], position_history: {},
    age_expired_book_count: 0, skew_rejected_book_count: 0, disconnected_book_count: 0,
    one_leg_unwind_attempt_count: 0, one_leg_unwind_failure_count: 0, partial_exposure_count: 0,
    partial_exposure_gross_notional: 0, partial_exposure_unrealized_pnl: 0, partial_exposure_entry_fees: 0,
    partial_exposure_reserved_margin: 0,
    candidate_funnel_counts: {
      observed_route_occurrence: 10, feature_ready_occurrence: 10, ev_qualified_occurrence: 0,
      unique_candidate: 0, duplicate_rejected: 0, cooldown_rejected: 0, capacity_rejected: 0,
      margin_rejected: 0, depth_rejected: 0, reprice_ev_rejected: 0, pending_created: 0,
      no_causal_fill: 0, post_fill_rejected: 0, execution_abort: 0, paired_open: 0,
    },
    stream_error_counts: {}, stream_error_counts_by_venue: {},
    paired_realized_pnl: 0, non_paired_execution_pnl: 0, account_pnl_reconciliation_error: 0,
    abort_count: 0, abort_gross_pnl: 0, abort_fees: 0, abort_net_pnl: 0,
    paired_fee_drag: 0, non_paired_fee_drag: 0, total_fee_drag: 0, runtime_hours: 1,
    paired_trades_per_hour: 0, paired_pnl_per_hour: 0, account_pnl_per_hour: 0,
    abort_count_per_hour: 0, abort_loss_per_hour: 0, rolling_1h_pnl: 0, rolling_3h_pnl: 0, rolling_6h_pnl: 0,
    median_entry_gap_seconds: null, p95_entry_gap_seconds: null,
    opportunity_radar: [{
      symbol: "BNB/USDT:USDT",
      buy_venue: "okx",
      sell_venue: "mexc",
      gross_edge_bps: 18.94,
      baseline_60m_bps: 17.45,
      baseline_15m_bps: 17.46,
      capture_bps: 1.48,
      conditional_pair_value_bps: 3.2,
      reject_net_bps: -14.5,
      expected_attempt_ev_bps: 0.52,
      minimum_required_ev_bps: 0.25,
      p_open: 0.18,
      estimated_accept_probability: 0.91,
      post_fill_accept_probability: 0.76,
      execution_calibration_global_fills: 14,
      execution_calibration_local_fills: 4,
      price_volatility_bps: 2.1,
      proposed_leverage: 20,
      signal_status: "TRADEABLE",
      decision: "V21_RISK_ADJUSTED_EV_ACCEPTED",
      secret: "drop-me",
    }],
  });

  assert.ok(sanitized);
  const row = sanitized.opportunity_radar[0];
  assert.equal(row.baseline_60m_bps, 17.45);
  assert.equal(row.capture_bps, 1.48);
  assert.equal(row.conditional_pair_value_bps, 3.2);
  assert.equal(row.reject_net_bps, -14.5);
  assert.equal(row.expected_attempt_ev_bps, 0.52);
  assert.equal(row.p_open, 0.18);
  assert.equal(row.estimated_accept_probability, 0.91);
  assert.equal(row.post_fill_accept_probability, 0.76);
  assert.equal(row.execution_calibration_global_fills, 14);
  assert.equal(row.execution_calibration_local_fills, 4);
  assert.equal(row.proposed_leverage, 20);
  assert.equal(sanitized.v21_shadow_accept_count, 26);
  assert.equal(sanitized.v21_shadow_reject_count, 518);
  assert.equal(sanitized.public_trade_update_count, 4321);
  assert.deepEqual(sanitized.public_trade_update_counts_by_venue, { okx: 4000, gate: 321 });
  assert.equal("secret" in row, false);
  const diagnostics = sanitizeTelemetry({ ...sanitized, expected_venue_count: 7,
    target_realized_pnl_per_hour: 0.5, funding_refresh_age_seconds: 30,
    stream_errors_last_60s_by_venue: { kucoin: 3, okx: -1 } });
  assert.equal(diagnostics.expected_venue_count, 7);
  assert.equal(diagnostics.target_realized_pnl_per_hour, 0.5);
  assert.equal(diagnostics.funding_refresh_age_seconds, 30);
  assert.deepEqual(diagnostics.stream_errors_last_60s_by_venue, { kucoin: 3 });
  const research = sanitizeTelemetry({ ...sanitized, funding_carry_research: {
    mode: "OBSERVATION_ONLY", sampled_at_ms: 1000000, fresh_quote_count: 14,
    asynchronous_pair_count: 4, positive_after_fee_quote_count: 1, realized_pnl: 999,
    rows: [{ symbol: "BTC/USDT:USDT", long_venue: "binance", short_venue: "okx",
      settlement_at_ms: 4600000, quoted_funding_bps: 25, round_trip_fee_bps: 20,
      after_fee_quote_bps: 5, secret: "never publish" }, { symbol: "invalid" }],
  } });
  assert.equal(research.funding_carry_research.mode, "OBSERVATION_ONLY");
  assert.equal(research.funding_carry_research.rows.length, 1);
  assert.equal(research.funding_carry_research.rows[0].after_fee_quote_bps, 5);
  assert.equal("realized_pnl" in research.funding_carry_research, false);
  assert.equal("secret" in research.funding_carry_research.rows[0], false);
  assert.equal(research.realized_pnl, sanitized.realized_pnl);
});
