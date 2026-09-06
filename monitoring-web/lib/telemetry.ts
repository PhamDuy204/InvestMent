export const TELEMETRY_SCHEMA_VERSION = "v13-monitoring-1";
export const V14_TELEMETRY_SCHEMA_VERSION = "v14-monitoring-1";
export const V15_TELEMETRY_SCHEMA_VERSION = "v15-monitoring-1";
export const V16_TELEMETRY_SCHEMA_VERSION = "v16-monitoring-1";
export const V17_TELEMETRY_SCHEMA_VERSION = "v17-monitoring-1";
export const V18_TELEMETRY_SCHEMA_VERSION = "v18-monitoring-1";
export const V19_TELEMETRY_SCHEMA_VERSION = "v19-monitoring-1";
export const V20_TELEMETRY_SCHEMA_VERSION = "v20-monitoring-1";
export const V21_TELEMETRY_SCHEMA_VERSION = "v21-monitoring-1";
export const STALE_AFTER_MS = 120_000;
export const LIVE_POLL_MS = 2_000;

export type DisplayStatus = "HEALTHY" | "STALE" | "DEGRADED" | "WAITING";
export type FundingCarryResearch = {
  mode: "OBSERVATION_ONLY";
  sampled_at_ms: number;
  fresh_quote_count: number;
  asynchronous_pair_count: number;
  positive_after_fee_quote_count: number;
  rows: { symbol: string; long_venue: string; short_venue: string; settlement_at_ms: number;
    quoted_funding_bps: number; round_trip_fee_bps: number; after_fee_quote_bps: number }[];
};
export type TelemetrySchemaVersion = typeof TELEMETRY_SCHEMA_VERSION | typeof V14_TELEMETRY_SCHEMA_VERSION | typeof V15_TELEMETRY_SCHEMA_VERSION | typeof V16_TELEMETRY_SCHEMA_VERSION | typeof V17_TELEMETRY_SCHEMA_VERSION | typeof V18_TELEMETRY_SCHEMA_VERSION | typeof V19_TELEMETRY_SCHEMA_VERSION | typeof V20_TELEMETRY_SCHEMA_VERSION | typeof V21_TELEMETRY_SCHEMA_VERSION;

export type PositionTelemetry = {
  position_id?: string;
  symbol?: string;
  long_exchange?: string;
  short_exchange?: string;
  quantity?: number;
  opened_at?: string;
  closed_at?: string;
  held_seconds?: number;
  close_reason?: string;
  long_entry_vwap?: number;
  short_entry_vwap?: number;
  long_entry_notional?: number;
  short_entry_notional?: number;
  long_fee_bps?: number;
  short_fee_bps?: number;
  mark_status?: string;
  mark_updated_at_utc?: string;
  long_current_vwap?: number;
  short_current_vwap?: number;
  long_unrealized_pnl?: number;
  short_unrealized_pnl?: number;
  gross_unrealized_pnl?: number;
  estimated_exit_fees?: number;
  estimated_net_pnl_if_closed?: number;
  current_spread_bps?: number;
  entry_gross_exposure?: number;
  current_gross_exposure?: number;
  exposure_pct_of_equity?: number;
  strategy_id?: string;
  raw_net_edge_bps?: number;
  entry_baseline_bps?: number;
  entry_excess_spread_bps?: number;
  entry_excess_after_cost_bps?: number;
  entry_fee_hurdle_bps?: number;
  entry_z_score?: number;
  entry_route_sigma_bps?: number;
  entry_short_slope_bps_per_min?: number;
  entry_price_volatility_bps?: number;
  entry_expected_value_bps?: number;
  entry_minimum_ev_bps?: number;
  entry_capture_bps?: number;
  entry_baseline_15m_bps?: number;
  entry_baseline_5m_bps?: number;
  entry_fill_probability?: number;
  entry_execution_mode?: string;
  long_entry_liquidity?: string;
  short_entry_liquidity?: string;
  entry_hedge_delay_ms?: number;
  long_entry_fee_bps?: number;
  short_entry_fee_bps?: number;
  exit_execution_mode?: string;
  long_exit_liquidity?: string;
  short_exit_liquidity?: string;
  pair_gross_fraction?: number;
  margin_model?: string;
  leverage?: number;
  long_initial_margin?: number;
  short_initial_margin?: number;
  initial_margin?: number;
  long_exit_vwap?: number;
  short_exit_vwap?: number;
  entry_fees?: number;
  exit_fees?: number;
  gross_pnl?: number;
  realized_net_pnl?: number;
  long_realized_net_pnl?: number;
  short_realized_net_pnl?: number;
  initial_net_edge_bps?: number;
  remaining_spread_bps?: number;
  actual_gross_spread_bps?: number;
  actual_capture_bps?: number;
  post_fill_expected_value_bps?: number;
  post_fill_decision?: string;
  status?: string;
};

export type OpportunityRadarRow = {
  symbol?: string;
  available_venues?: string[];
  venue_count?: number;
  decision?: string;
  buy_venue?: string;
  sell_venue?: string;
  gross_edge_bps?: number;
  total_fee_bps?: number;
  safety_buffer_bps?: number;
  best_net_edge_bps?: number;
  signal_status?: string;
  edge_to_trade_bps?: number;
  optimizer_score_bps?: number;
  optimizer_rank?: number;
  baseline_bps?: number;
  route_sigma_bps?: number;
  excess_spread_bps?: number;
  fee_hurdle_bps?: number;
  excess_after_cost_bps?: number;
  z_score?: number;
  short_slope_bps_per_min?: number;
  medium_slope_bps_per_min?: number;
  price_volatility_bps?: number;
  history_sample_count?: number;
  history_span_seconds?: number;
  proposed_leverage?: number;
  proposed_pair_gross_fraction?: number;
  proposed_target_notional?: number;
  baseline_60m_bps?: number;
  baseline_15m_bps?: number;
  baseline_5m_bps?: number;
  structural_excess_bps?: number;
  local_excess_bps?: number;
  fast_excess_bps?: number;
  capture_bps?: number;
  expected_value_bps?: number;
  minimum_required_ev_bps?: number;
  p_open?: number;
  p_one_leg?: number;
  long_fill_probability?: number;
  short_fill_probability?: number;
  long_exit_fill_probability?: number;
  short_exit_fill_probability?: number;
  expected_entry_fee_bps?: number;
  expected_exit_fee_bps?: number;
  adverse_selection_bps?: number;
  hedge_risk_bps?: number;
  four_taker_hurdle_bps?: number;
  maker_round_trip_hurdle_bps?: number;
  long_quote_spread_bps?: number;
  short_quote_spread_bps?: number;
  expected_entry_price_improvement_bps?: number;
  expected_exit_price_improvement_bps?: number;
  persistence_sample_count?: number;
  persistence_seconds?: number;
  spread_slope_bps_per_min?: number;
  funding_status?: string;
  funding_edge_bps?: number;
  maker_side?: string;
  maker_venue?: string;
  hedge_venue?: string;
  post_fill_accept_probability?: number;
  estimated_accept_probability?: number;
  reject_net_bps?: number;
  expected_attempt_ev_bps?: number;
  conditional_pair_value_bps?: number;
  max_conditional_pair_value_bps?: number;
  conditional_fill_value_bps?: number;
  execution_calibration_global_fills?: number;
  execution_calibration_local_fills?: number;
};

export type StrategyLabRow = {
  strategy_id: string;
  mode?: string;
  open_position_count?: number;
  closed_trade_count?: number;
  realized_pnl?: number;
  win_rate_pct?: number | null;
  profit_factor?: number | null;
  observed_route_count?: number;
};

export type AccountHistoryPoint = {
  observed_at_ms: number;
  realized_equity: number;
  marked_equity: number;
  realized_pnl: number;
  unrealized_net_pnl: number;
  gross_exposure: number;
  margin_used: number;
  modeled_fee_drag: number;
};

export type PositionHistoryPoint = {
  observed_at_ms: number;
  symbol: string;
  spread_bps: number;
  net_pnl: number;
  baseline_bps?: number;
};

export type PendingExecutionTelemetry = {
  pending_id?: string;
  position_id?: string;
  symbol?: string;
  long_exchange?: string;
  short_exchange?: string;
  quantity?: number;
  placed_at_utc?: string;
  status?: string;
  long_limit_price?: number;
  short_limit_price?: number;
  expected_value_bps?: number;
  minimum_required_ev_bps?: number;
  capture_bps?: number;
  p_open?: number;
  leverage?: number;
  pair_gross_fraction?: number;
  reason?: string;
  filled_side?: string;
  filled_venue?: string;
  cancelled_maker_leg?: string;
  unwind_reason?: string;
  unwind_pending_since_utc?: string;
  partial_entry_price?: number;
  partial_entry_notional?: number;
  partial_entry_fee_bps?: number;
  partial_entry_fee?: number;
  partial_gross_notional?: number;
  partial_gross_unrealized_pnl?: number;
  partial_unrealized_pnl?: number;
  partial_initial_margin?: number;
  partial_mark_status?: string;
  partial_current_vwap?: number;
  partial_estimated_exit_fee?: number;
  partial_estimated_net_pnl_if_unwound?: number;
  unwind_attempt_count?: number;
  unwind_failure_count?: number;
  maker_side?: string;
};

export type MonitoringMetrics = {
  win_rate_pct: number | null;
  profit_factor: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  fee_drag: number | null;
  avg_holding_seconds: number | null;
  max_drawdown_pct: number | null;
  opportunity_to_trade_pct: number | null;
  closed_trade_count: number;
};

export type MonitoringTelemetry = {
  schema_version: TelemetrySchemaVersion;
  updated_at_utc: string;
  runner_health: string;
  runner_error: string | null;
  initial_equity: number;
  equity: number;
  realized_pnl: number;
  return_pct: number;
  scan_count: number;
  opened_position_count: number;
  closed_position_count: number;
  open_position_count: number;
  open_positions: PositionTelemetry[];
  closed_positions: PositionTelemetry[];
  metrics: MonitoringMetrics;
  margin_model?: string;
  portfolio_model?: string;
  maintenance_stress_rate?: number;
  margin_utilization_cap?: number;
  venue_concentration_penalty_bps?: number;
  maintenance_stress_used?: number;
  min_stress_margin_ratio?: number | null;
  exchange_leverage?: number;
  gross_leverage_cap?: number;
  gross_leverage_used?: number;
  gross_exposure?: number;
  initial_margin_used?: number;
  available_margin?: number;
  max_open_positions?: number;
  single_pair_gross_fraction?: number;
  qualified_opportunity_count?: number;
  observed_signal_count?: number;
  last_cycle_signal_count?: number;
  last_cycle_tradeable_count?: number;
  venue_balances?: Record<string, number>;
  venue_margin_used?: Record<string, number>;
  venue_available_margin?: Record<string, number>;
  venue_account_equity?: Record<string, number>;
  venue_unrealized_pnl?: Record<string, number>;
  venue_maintenance_stress?: Record<string, number>;
  venue_margin_ratio?: Record<string, number>;
  venue_margin_utilization?: Record<string, number>;
  universe_size?: number;
  opportunity_radar?: OpportunityRadarRow[];
  invariant_failure_count?: number;
  started_at_utc?: string;
  shadow_updated_at_utc?: string;
  strategy_lab?: StrategyLabRow[];
  account_history?: AccountHistoryPoint[];
  position_history?: Record<string, PositionHistoryPoint[]>;
  pending_entry_count?: number;
  pending_exit_count?: number;
  pending_entries?: PendingExecutionTelemetry[];
  pending_exits?: PendingExecutionTelemetry[];
  maker_probe_count?: number;
  maker_fill_observation_count?: number;
  maker_entry_cancel_count?: number;
  one_leg_hedge_count?: number;
  maker_exit_fallback_count?: number;
  maker_hedge_failure_count?: number;
  post_fill_accept_count?: number;
  post_fill_reject_count?: number;
  v21_shadow_accept_count?: number;
  v21_shadow_reject_count?: number;
  public_trade_update_count?: number;
  public_trade_update_counts_by_venue?: Record<string, number>;
  both_maker_fill_count?: number;
  one_leg_abort_count?: number;
  one_leg_abort_pnl?: number;
  book_update_count?: number;
  ws_reconnect_count?: number;
  book_cache_entry_count?: number;
  fresh_book_count?: number;
  stale_book_count?: number;
  connected_venue_count?: number;
  expected_venue_count?: number;
  target_realized_pnl_per_hour?: number;
  funding_refresh_age_seconds?: number | null;
  stream_errors_last_60s_by_venue?: Record<string, number>;
  funding_carry_research?: FundingCarryResearch;
  book_age_ms_median?: number | null;
  book_age_ms_max?: number | null;
  memory_prune_count?: number;
  process_rss_bytes?: number;
  age_expired_book_count?: number;
  skew_rejected_book_count?: number;
  disconnected_book_count?: number;
  one_leg_unwind_attempt_count?: number;
  one_leg_unwind_failure_count?: number;
  partial_exposure_count?: number;
  partial_exposure_gross_notional?: number;
  partial_exposure_unrealized_pnl?: number;
  partial_exposure_entry_fees?: number;
  partial_exposure_reserved_margin?: number;
  candidate_funnel_counts?: Record<string, number>;
  stream_error_counts?: Record<string, number>;
  stream_error_counts_by_venue?: Record<string, Record<string, number>>;
  paired_realized_pnl?: number;
  non_paired_execution_pnl?: number;
  account_pnl_reconciliation_error?: number;
  abort_count?: number;
  abort_gross_pnl?: number;
  abort_fees?: number;
  abort_net_pnl?: number;
  realized_funding_pnl?: number;
  funding_pnl_per_hour?: number;
  paired_fee_drag?: number;
  non_paired_fee_drag?: number;
  total_fee_drag?: number;
  runtime_hours?: number;
  paired_trades_per_hour?: number;
  paired_pnl_per_hour?: number;
  account_pnl_per_hour?: number;
  abort_count_per_hour?: number;
  abort_loss_per_hour?: number;
  rolling_1h_pnl?: number;
  rolling_3h_pnl?: number;
  rolling_6h_pnl?: number;
  median_entry_gap_seconds?: number | null;
  p95_entry_gap_seconds?: number | null;
};

export type Telemetry = MonitoringTelemetry;

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

const POSITION_KEYS = [
  "position_id", "symbol", "long_exchange", "short_exchange", "quantity", "opened_at", "closed_at",
  "held_seconds", "close_reason", "long_entry_vwap", "short_entry_vwap", "long_entry_notional",
  "short_entry_notional", "long_fee_bps", "short_fee_bps", "long_exit_vwap", "short_exit_vwap",
  "entry_fees", "exit_fees", "gross_pnl", "realized_net_pnl", "long_realized_net_pnl", "short_realized_net_pnl",
  "initial_net_edge_bps", "remaining_spread_bps", "mark_status", "mark_updated_at_utc", "long_current_vwap",
  "short_current_vwap", "long_unrealized_pnl", "short_unrealized_pnl", "gross_unrealized_pnl",
  "estimated_exit_fees", "estimated_net_pnl_if_closed", "current_spread_bps", "entry_gross_exposure",
  "current_gross_exposure", "exposure_pct_of_equity", "strategy_id", "raw_net_edge_bps", "entry_baseline_bps",
  "entry_excess_spread_bps", "entry_excess_after_cost_bps", "entry_fee_hurdle_bps", "entry_z_score",
  "entry_route_sigma_bps", "entry_short_slope_bps_per_min", "entry_price_volatility_bps",
  "entry_expected_value_bps", "entry_minimum_ev_bps", "entry_capture_bps", "entry_baseline_15m_bps", "entry_baseline_5m_bps",
  "entry_fill_probability", "entry_execution_mode", "long_entry_liquidity", "short_entry_liquidity", "entry_hedge_delay_ms",
  "long_entry_fee_bps", "short_entry_fee_bps", "exit_execution_mode", "long_exit_liquidity", "short_exit_liquidity", "pair_gross_fraction",
  "margin_model", "leverage", "long_initial_margin",
  "short_initial_margin", "initial_margin", "actual_gross_spread_bps", "actual_capture_bps",
  "post_fill_expected_value_bps", "post_fill_decision", "status",
] as const;

const RADAR_KEYS = [
  "symbol", "venue_count", "decision", "buy_venue", "sell_venue", "gross_edge_bps", "total_fee_bps",
  "safety_buffer_bps", "best_net_edge_bps", "signal_status", "edge_to_trade_bps", "optimizer_score_bps", "optimizer_rank",
  "baseline_bps", "route_sigma_bps", "excess_spread_bps", "fee_hurdle_bps", "excess_after_cost_bps", "z_score",
  "short_slope_bps_per_min", "medium_slope_bps_per_min", "price_volatility_bps", "history_sample_count",
  "history_span_seconds", "proposed_leverage", "proposed_pair_gross_fraction", "proposed_target_notional",
  "baseline_60m_bps", "baseline_15m_bps", "baseline_5m_bps", "structural_excess_bps", "local_excess_bps", "fast_excess_bps",
  "capture_bps", "expected_value_bps", "minimum_required_ev_bps", "p_open", "p_one_leg", "long_fill_probability",
  "short_fill_probability", "long_exit_fill_probability", "short_exit_fill_probability", "expected_entry_fee_bps", "expected_exit_fee_bps",
  "adverse_selection_bps", "hedge_risk_bps", "four_taker_hurdle_bps", "maker_round_trip_hurdle_bps",
  "long_quote_spread_bps", "short_quote_spread_bps", "expected_entry_price_improvement_bps", "expected_exit_price_improvement_bps",
  "persistence_sample_count", "persistence_seconds", "spread_slope_bps_per_min", "funding_status", "funding_edge_bps",
  "maker_side", "maker_venue", "hedge_venue", "post_fill_accept_probability", "estimated_accept_probability", "reject_net_bps", "expected_attempt_ev_bps",
  "conditional_pair_value_bps", "max_conditional_pair_value_bps", "conditional_fill_value_bps", "execution_calibration_global_fills", "execution_calibration_local_fills",
] as const;

function sanitizePosition(source: unknown): PositionTelemetry {
  if (!isRecord(source)) return {};
  const output: Record<string, string | number> = {};
  for (const key of POSITION_KEYS) {
    const value = source[key];
    if (typeof value === "string" || isFiniteNumber(value)) output[key] = value;
  }
  return output as PositionTelemetry;
}

function sanitizeNumberMap(source: unknown): Record<string, number> {
  if (!isRecord(source)) return {};
  return Object.fromEntries(
    Object.entries(source).filter((entry): entry is [string, number] => isFiniteNumber(entry[1])).slice(0, 20),
  );
}

const V21_PUBLIC_TRADE_VENUES = ["okx", "gate"] as const;

const V19_CANDIDATE_FUNNEL_KEYS = [
  "observed_route_occurrence", "feature_ready_occurrence", "ev_qualified_occurrence", "unique_candidate",
  "duplicate_rejected", "cooldown_rejected", "capacity_rejected", "margin_rejected", "depth_rejected",
  "reprice_ev_rejected", "pending_created", "no_causal_fill", "post_fill_rejected", "execution_abort", "paired_open",
] as const;

const V19_STREAM_ERROR_REASON_KEYS = [
  "KeyError", "TimeoutError", "ConnectionError", "OSError", "RuntimeError", "ValueError", "TypeError",
  "NetworkError", "ExchangeError", "RequestTimeout", "ExchangeNotAvailable", "DDoSProtection",
  "RateLimitExceeded", "InvalidNonce", "BadRequest", "BadSymbol", "NotSupported", "OperationFailed",
  "OperationRejected", "AuthenticationError", "Exception", "Other",
] as const;

function sanitizeAllowedNumberMap(
  source: unknown,
  allowedKeys: readonly string[],
): Record<string, number> {
  if (!isRecord(source)) return {};
  const output: Record<string, number> = {};
  for (const key of allowedKeys) {
    const value = source[key];
    if (isFiniteNumber(value) && value >= 0) output[key] = value;
  }
  return output;
}

function sanitizeStreamErrorCountsByVenue(source: unknown): Record<string, Record<string, number>> {
  if (!isRecord(source)) return {};
  const output: Record<string, Record<string, number>> = {};
  for (const [venue, rawCounts] of Object.entries(source).slice(0, 32)) {
    const counts = sanitizeAllowedNumberMap(rawCounts, V19_STREAM_ERROR_REASON_KEYS);
    if (Object.keys(counts).length) output[venue.slice(0, 64)] = counts;
  }
  return output;
}

function sanitizeFundingCarryResearch(source: unknown): FundingCarryResearch | undefined {
  if (!isRecord(source) || source.mode !== "OBSERVATION_ONLY") return undefined;
  const counters = ["sampled_at_ms", "fresh_quote_count", "asynchronous_pair_count", "positive_after_fee_quote_count"] as const;
  if (counters.some((key) => !isFiniteNumber(source[key]) || (source[key] as number) < 0)) return undefined;
  const venues = ["binance", "bybit", "bitget", "okx", "gate", "kucoin", "mexc"];
  const rows: FundingCarryResearch["rows"] = [];
  for (const row of Array.isArray(source.rows) ? source.rows.slice(0, 6) : []) {
    if (!isRecord(row) || typeof row.symbol !== "string" || row.symbol.length > 80
      || typeof row.long_venue !== "string" || !venues.includes(row.long_venue)
      || typeof row.short_venue !== "string" || !venues.includes(row.short_venue)
      || row.long_venue === row.short_venue) continue;
    const keys = ["settlement_at_ms", "quoted_funding_bps", "round_trip_fee_bps", "after_fee_quote_bps"] as const;
    if (keys.some((key) => !isFiniteNumber(row[key])) || (row.settlement_at_ms as number) <= 0
      || (row.settlement_at_ms as number) > 8.64e15 || (row.round_trip_fee_bps as number) < 0) continue;
    rows.push({ symbol: row.symbol, long_venue: row.long_venue, short_venue: row.short_venue,
      settlement_at_ms: row.settlement_at_ms as number, quoted_funding_bps: row.quoted_funding_bps as number,
      round_trip_fee_bps: row.round_trip_fee_bps as number, after_fee_quote_bps: row.after_fee_quote_bps as number });
  }
  return { mode: "OBSERVATION_ONLY", sampled_at_ms: source.sampled_at_ms as number,
    fresh_quote_count: source.fresh_quote_count as number, asynchronous_pair_count: source.asynchronous_pair_count as number,
    positive_after_fee_quote_count: source.positive_after_fee_quote_count as number, rows };
}

function sanitizeRadar(source: unknown): OpportunityRadarRow[] {
  if (!Array.isArray(source)) return [];
  return source.slice(0, 100).flatMap((value) => {
    if (!isRecord(value)) return [];
    const row: Record<string, string | number | string[]> = {};
    for (const key of RADAR_KEYS) {
      const field = value[key];
      if (typeof field === "string" || isFiniteNumber(field)) row[key] = field;
    }
    if (Array.isArray(value.available_venues)) {
      row.available_venues = value.available_venues.filter((item): item is string => typeof item === "string").slice(0, 10);
    }
    return [row as OpportunityRadarRow];
  });
}

const V15_STRATEGY_IDS = new Set([
  "CONTROL_V14C",
  "ADAPTIVE_EXIT_SHADOW_V1",
  "SPREAD_CONTINUATION_SHADOW_V1",
  "FUNDING_AWARE_SHADOW_V1",
]);

const STRATEGY_KEYS = [
  "strategy_id", "mode", "open_position_count", "closed_trade_count", "realized_pnl",
  "win_rate_pct", "profit_factor", "observed_route_count",
] as const;

function sanitizeStrategyLab(source: unknown): StrategyLabRow[] {
  if (!Array.isArray(source)) return [];
  return source.flatMap((value) => {
    if (!isRecord(value) || typeof value.strategy_id !== "string" || !V15_STRATEGY_IDS.has(value.strategy_id)) return [];
    const row: Record<string, string | number | null> = {};
    for (const key of STRATEGY_KEYS) {
      const field = value[key];
      if (typeof field === "string" || isFiniteNumber(field) || (field === null && (key === "win_rate_pct" || key === "profit_factor"))) {
        row[key] = field as string | number | null;
      }
    }
    return [row as StrategyLabRow];
  });
}

const ACCOUNT_HISTORY_KEYS = [
  "observed_at_ms", "realized_equity", "marked_equity", "realized_pnl", "unrealized_net_pnl",
  "gross_exposure", "margin_used", "modeled_fee_drag",
] as const;

function sanitizeAccountHistory(source: unknown): AccountHistoryPoint[] {
  if (!Array.isArray(source)) return [];
  return source.slice(-360).flatMap((value) => {
    if (!isRecord(value) || ACCOUNT_HISTORY_KEYS.some((key) => !isFiniteNumber(value[key]))) return [];
    return [{
      observed_at_ms: value.observed_at_ms as number,
      realized_equity: value.realized_equity as number,
      marked_equity: value.marked_equity as number,
      realized_pnl: value.realized_pnl as number,
      unrealized_net_pnl: value.unrealized_net_pnl as number,
      gross_exposure: value.gross_exposure as number,
      margin_used: value.margin_used as number,
      modeled_fee_drag: value.modeled_fee_drag as number,
    }];
  });
}

function sanitizePositionHistory(source: unknown): Record<string, PositionHistoryPoint[]> {
  if (!isRecord(source)) return {};
  const output: Record<string, PositionHistoryPoint[]> = {};
  for (const [positionId, samples] of Object.entries(source).slice(0, 64)) {
    if (!positionId || !Array.isArray(samples)) continue;
    const clean = samples.slice(-120).flatMap((value) => {
      if (!isRecord(value) || typeof value.symbol !== "string") return [];
      if (![value.observed_at_ms, value.spread_bps, value.net_pnl].every(isFiniteNumber)) return [];
      if (value.baseline_bps !== undefined && !isFiniteNumber(value.baseline_bps)) return [];
      return [{
        observed_at_ms: value.observed_at_ms as number,
        symbol: value.symbol,
        spread_bps: value.spread_bps as number,
        net_pnl: value.net_pnl as number,
        ...(isFiniteNumber(value.baseline_bps) ? { baseline_bps: value.baseline_bps } : {}),
      }];
    });
    if (clean.length) output[positionId.slice(0, 128)] = clean;
  }
  return output;
}

const PENDING_KEYS = [
  "pending_id", "position_id", "symbol", "long_exchange", "short_exchange", "quantity", "placed_at_utc", "status",
  "long_limit_price", "short_limit_price", "expected_value_bps", "minimum_required_ev_bps", "capture_bps", "p_open",
  "leverage", "pair_gross_fraction", "reason", "filled_side", "filled_venue", "cancelled_maker_leg",
  "unwind_reason", "unwind_pending_since_utc", "partial_entry_price", "partial_entry_notional", "partial_entry_fee_bps", "partial_entry_fee",
  "partial_gross_notional", "partial_gross_unrealized_pnl", "partial_unrealized_pnl", "partial_initial_margin",
  "partial_mark_status", "partial_current_vwap", "partial_estimated_exit_fee",
  "partial_estimated_net_pnl_if_unwound", "unwind_attempt_count", "unwind_failure_count", "maker_side",
] as const;

function sanitizePending(source: unknown): PendingExecutionTelemetry[] {
  if (!Array.isArray(source)) return [];
  return source.slice(0, 32).flatMap((value) => {
    if (!isRecord(value)) return [];
    const row: Record<string, string | number> = {};
    for (const key of PENDING_KEYS) {
      const field = value[key];
      if (typeof field === "string" || isFiniteNumber(field)) row[key] = field;
    }
    return [row as PendingExecutionTelemetry];
  });
}

function sanitizeMetrics(source: unknown): MonitoringMetrics | null {
  if (!isRecord(source)) return null;
  const nullable = [
    "win_rate_pct", "profit_factor", "avg_win", "avg_loss", "fee_drag",
    "avg_holding_seconds", "max_drawdown_pct", "opportunity_to_trade_pct",
  ] as const;
  for (const key of nullable) {
    if (source[key] !== null && !isFiniteNumber(source[key])) return null;
  }
  if (!isFiniteNumber(source.closed_trade_count)) return null;
  return {
    win_rate_pct: source.win_rate_pct as number | null,
    profit_factor: source.profit_factor as number | null,
    avg_win: source.avg_win as number | null,
    avg_loss: source.avg_loss as number | null,
    fee_drag: source.fee_drag as number | null,
    avg_holding_seconds: source.avg_holding_seconds as number | null,
    max_drawdown_pct: source.max_drawdown_pct as number | null,
    opportunity_to_trade_pct: source.opportunity_to_trade_pct as number | null,
    closed_trade_count: source.closed_trade_count,
  };
}

export function sanitizeTelemetry(value: unknown): MonitoringTelemetry | null {
  if (!isRecord(value)) return null;
  if (
    value.schema_version !== TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V14_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V15_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V16_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V17_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V18_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V19_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V20_TELEMETRY_SCHEMA_VERSION &&
    value.schema_version !== V21_TELEMETRY_SCHEMA_VERSION
  ) return null;
  if (typeof value.updated_at_utc !== "string" || !Number.isFinite(Date.parse(value.updated_at_utc))) return null;
  if (typeof value.runner_health !== "string") return null;
  if (value.runner_error !== null && typeof value.runner_error !== "string") return null;
  for (const key of [
    "initial_equity", "equity", "realized_pnl", "return_pct", "scan_count",
    "opened_position_count", "closed_position_count", "open_position_count",
  ] as const) {
    if (!isFiniteNumber(value[key])) return null;
  }
  if (!Array.isArray(value.open_positions) || !Array.isArray(value.closed_positions)) return null;
  const metrics = sanitizeMetrics(value.metrics);
  if (!metrics) return null;

  const telemetry: MonitoringTelemetry = {
    schema_version: value.schema_version,
    updated_at_utc: value.updated_at_utc,
    runner_health: value.runner_health,
    runner_error: value.runner_error ? value.runner_error.slice(0, 240) : null,
    initial_equity: value.initial_equity as number,
    equity: value.equity as number,
    realized_pnl: value.realized_pnl as number,
    return_pct: value.return_pct as number,
    scan_count: value.scan_count as number,
    opened_position_count: value.opened_position_count as number,
    closed_position_count: value.closed_position_count as number,
    open_position_count: value.open_position_count as number,
    open_positions: value.open_positions.map(sanitizePosition),
    closed_positions: value.closed_positions.slice(-200).map(sanitizePosition),
    metrics,
  };

  if (
    value.schema_version === V14_TELEMETRY_SCHEMA_VERSION ||
    value.schema_version === V15_TELEMETRY_SCHEMA_VERSION ||
    value.schema_version === V16_TELEMETRY_SCHEMA_VERSION ||
    value.schema_version === V17_TELEMETRY_SCHEMA_VERSION ||
    value.schema_version === V18_TELEMETRY_SCHEMA_VERSION ||
    value.schema_version === V19_TELEMETRY_SCHEMA_VERSION ||
    (value.schema_version === V20_TELEMETRY_SCHEMA_VERSION || value.schema_version === V21_TELEMETRY_SCHEMA_VERSION)
  ) {
    const requiredNumbers = [
      "exchange_leverage", "gross_leverage_cap", "gross_leverage_used", "gross_exposure", "initial_margin_used",
      "available_margin", "max_open_positions", "single_pair_gross_fraction", "qualified_opportunity_count",
      "observed_signal_count", "last_cycle_signal_count", "last_cycle_tradeable_count",
      "universe_size", "invariant_failure_count",
    ] as const;
    if (typeof value.margin_model !== "string" || requiredNumbers.some((key) => !isFiniteNumber(value[key]))) return null;
    telemetry.margin_model = value.margin_model;
    for (const key of requiredNumbers) telemetry[key] = value[key] as never;
    if (typeof value.portfolio_model === "string") telemetry.portfolio_model = value.portfolio_model;
    for (const key of [
      "maintenance_stress_rate", "margin_utilization_cap", "venue_concentration_penalty_bps", "maintenance_stress_used",
    ] as const) {
      if (isFiniteNumber(value[key])) telemetry[key] = value[key] as never;
    }
    telemetry.min_stress_margin_ratio = value.min_stress_margin_ratio === null
      ? null
      : isFiniteNumber(value.min_stress_margin_ratio) ? value.min_stress_margin_ratio : undefined;
    telemetry.venue_balances = sanitizeNumberMap(value.venue_balances);
    telemetry.venue_margin_used = sanitizeNumberMap(value.venue_margin_used);
    telemetry.venue_available_margin = sanitizeNumberMap(value.venue_available_margin);
    telemetry.venue_account_equity = sanitizeNumberMap(value.venue_account_equity);
    telemetry.venue_unrealized_pnl = sanitizeNumberMap(value.venue_unrealized_pnl);
    telemetry.venue_maintenance_stress = sanitizeNumberMap(value.venue_maintenance_stress);
    telemetry.venue_margin_ratio = sanitizeNumberMap(value.venue_margin_ratio);
    telemetry.venue_margin_utilization = sanitizeNumberMap(value.venue_margin_utilization);
    telemetry.opportunity_radar = sanitizeRadar(value.opportunity_radar);
    telemetry.started_at_utc = typeof value.started_at_utc === "string" ? value.started_at_utc : "";
    if (value.schema_version === V15_TELEMETRY_SCHEMA_VERSION) {
      if (typeof value.shadow_updated_at_utc !== "string" || !Number.isFinite(Date.parse(value.shadow_updated_at_utc))) return null;
      if (!Array.isArray(value.strategy_lab)) return null;
      telemetry.shadow_updated_at_utc = value.shadow_updated_at_utc;
      telemetry.strategy_lab = sanitizeStrategyLab(value.strategy_lab);
    }
    if (value.schema_version === V16_TELEMETRY_SCHEMA_VERSION || value.schema_version === V17_TELEMETRY_SCHEMA_VERSION || value.schema_version === V18_TELEMETRY_SCHEMA_VERSION || value.schema_version === V19_TELEMETRY_SCHEMA_VERSION || (value.schema_version === V20_TELEMETRY_SCHEMA_VERSION || value.schema_version === V21_TELEMETRY_SCHEMA_VERSION)) {
      if (!Array.isArray(value.account_history) || !isRecord(value.position_history)) return null;
      telemetry.account_history = sanitizeAccountHistory(value.account_history);
      telemetry.position_history = sanitizePositionHistory(value.position_history);
    }
    if (value.schema_version === V17_TELEMETRY_SCHEMA_VERSION || value.schema_version === V18_TELEMETRY_SCHEMA_VERSION || value.schema_version === V19_TELEMETRY_SCHEMA_VERSION || (value.schema_version === V20_TELEMETRY_SCHEMA_VERSION || value.schema_version === V21_TELEMETRY_SCHEMA_VERSION)) {
      const counters = [
        "pending_entry_count", "pending_exit_count", "maker_probe_count", "maker_fill_observation_count",
        "maker_entry_cancel_count", "one_leg_hedge_count", "maker_exit_fallback_count", "maker_hedge_failure_count",
      ] as const;
      if (!Array.isArray(value.pending_entries) || !Array.isArray(value.pending_exits) || counters.some((key) => !isFiniteNumber(value[key]))) return null;
      for (const key of counters) telemetry[key] = value[key] as never;
      telemetry.pending_entries = sanitizePending(value.pending_entries);
      telemetry.pending_exits = sanitizePending(value.pending_exits);
    }
    if (value.schema_version === V18_TELEMETRY_SCHEMA_VERSION || value.schema_version === V19_TELEMETRY_SCHEMA_VERSION || (value.schema_version === V20_TELEMETRY_SCHEMA_VERSION || value.schema_version === V21_TELEMETRY_SCHEMA_VERSION)) {
      const v18Counters = [
        "post_fill_accept_count", "post_fill_reject_count", "both_maker_fill_count", "one_leg_abort_count",
        "book_update_count", "ws_reconnect_count", "book_cache_entry_count", "fresh_book_count",
        "stale_book_count", "connected_venue_count", "memory_prune_count", "process_rss_bytes",
      ] as const;
      if (v18Counters.some((key) => !isFiniteNumber(value[key])) || !isFiniteNumber(value.one_leg_abort_pnl)) return null;
      for (const key of v18Counters) telemetry[key] = value[key] as never;
      if (isFiniteNumber(value.expected_venue_count) && value.expected_venue_count >= 0) {
        telemetry.expected_venue_count = value.expected_venue_count;
      }
      telemetry.one_leg_abort_pnl = value.one_leg_abort_pnl as number;
      telemetry.book_age_ms_median = value.book_age_ms_median === null ? null : isFiniteNumber(value.book_age_ms_median) ? value.book_age_ms_median : undefined;
      telemetry.book_age_ms_max = value.book_age_ms_max === null ? null : isFiniteNumber(value.book_age_ms_max) ? value.book_age_ms_max : undefined;
    }
    if (value.schema_version === V21_TELEMETRY_SCHEMA_VERSION) {
      telemetry.funding_carry_research = sanitizeFundingCarryResearch(value.funding_carry_research);
      if (isFiniteNumber(value.target_realized_pnl_per_hour) && value.target_realized_pnl_per_hour >= 0) {
        telemetry.target_realized_pnl_per_hour = value.target_realized_pnl_per_hour;
      }
      telemetry.funding_refresh_age_seconds = value.funding_refresh_age_seconds === null ? null
        : isFiniteNumber(value.funding_refresh_age_seconds) && value.funding_refresh_age_seconds >= 0
          ? value.funding_refresh_age_seconds : undefined;
      telemetry.stream_errors_last_60s_by_venue = sanitizeAllowedNumberMap(
        value.stream_errors_last_60s_by_venue, ["binance", "bybit", "bitget", "okx", "gate", "kucoin", "mexc"],
      );
      const v21Counters = ["v21_shadow_accept_count", "v21_shadow_reject_count"] as const;
      if (v21Counters.some((key) => !isFiniteNumber(value[key]))) return null;
      for (const key of v21Counters) telemetry[key] = value[key] as never;
      telemetry.public_trade_update_count = isFiniteNumber(value.public_trade_update_count) ? value.public_trade_update_count : 0;
      telemetry.public_trade_update_counts_by_venue = sanitizeAllowedNumberMap(
        value.public_trade_update_counts_by_venue,
        V21_PUBLIC_TRADE_VENUES,
      );
    }
    if (value.schema_version === V19_TELEMETRY_SCHEMA_VERSION || (value.schema_version === V20_TELEMETRY_SCHEMA_VERSION || value.schema_version === V21_TELEMETRY_SCHEMA_VERSION)) {
      const causeCounters = [
        "age_expired_book_count", "skew_rejected_book_count", "disconnected_book_count",
        "one_leg_unwind_attempt_count", "one_leg_unwind_failure_count", "partial_exposure_count",
      ] as const;
      const partialExposureValues = [
        "partial_exposure_gross_notional", "partial_exposure_unrealized_pnl",
        "partial_exposure_entry_fees", "partial_exposure_reserved_margin",
      ] as const;
      const candidateFunnelCounts = value.candidate_funnel_counts;
      if (
        causeCounters.some((key) => !Number.isInteger(value[key]) || (value[key] as number) < 0) ||
        partialExposureValues.some((key) => !isFiniteNumber(value[key])) ||
        !isRecord(candidateFunnelCounts) ||
        V19_CANDIDATE_FUNNEL_KEYS.some(
          (key) => !Number.isInteger(candidateFunnelCounts[key]) ||
            (candidateFunnelCounts[key] as number) < 0,
        ) ||
        !isRecord(value.stream_error_counts) ||
        !isRecord(value.stream_error_counts_by_venue)
      ) return null;
      for (const key of causeCounters) telemetry[key] = value[key] as never;
      for (const key of partialExposureValues) telemetry[key] = value[key] as never;
      telemetry.candidate_funnel_counts = sanitizeAllowedNumberMap(
        value.candidate_funnel_counts,
        V19_CANDIDATE_FUNNEL_KEYS,
      );
      telemetry.stream_error_counts = sanitizeAllowedNumberMap(
        value.stream_error_counts,
        V19_STREAM_ERROR_REASON_KEYS,
      );
      telemetry.stream_error_counts_by_venue = sanitizeStreamErrorCountsByVenue(
        value.stream_error_counts_by_venue,
      );
    }
    if ((value.schema_version === V20_TELEMETRY_SCHEMA_VERSION || value.schema_version === V21_TELEMETRY_SCHEMA_VERSION)) {
      const accountFields = [
        "paired_realized_pnl", "non_paired_execution_pnl", "account_pnl_reconciliation_error",
        "abort_count", "abort_gross_pnl", "abort_fees", "abort_net_pnl",
        "paired_fee_drag", "non_paired_fee_drag", "total_fee_drag", "runtime_hours",
        "paired_trades_per_hour", "paired_pnl_per_hour", "account_pnl_per_hour",
        "abort_count_per_hour", "abort_loss_per_hour", "rolling_1h_pnl", "rolling_3h_pnl", "rolling_6h_pnl",
      ] as const;
      if (accountFields.some((key) => !isFiniteNumber(value[key]))) return null;
      for (const key of accountFields) telemetry[key] = value[key] as never;
      for (const key of ["realized_funding_pnl", "funding_pnl_per_hour"] as const) {
        const field = value[key];
        if (field !== undefined && !isFiniteNumber(field)) return null;
        if (field !== undefined) telemetry[key] = field;
      }
      for (const key of ["median_entry_gap_seconds", "p95_entry_gap_seconds"] as const) {
        const field = value[key];
        if (field !== null && !isFiniteNumber(field)) return null;
        telemetry[key] = field as number | null;
      }
    }
  }
  return telemetry;
}

export function validateTelemetry(value: unknown): { ok: true; data: MonitoringTelemetry } | { ok: false; error: string } {
  const data = sanitizeTelemetry(value);
  return data ? { ok: true, data } : { ok: false, error: "invalid telemetry" };
}

export function getDisplayStatus(telemetry: MonitoringTelemetry | null, nowMs = Date.now()): DisplayStatus {
  if (!telemetry) return "WAITING";
  const runnerHealth = telemetry.runner_health.toUpperCase();
  if (runnerHealth === "STALE") return "STALE";
  const updatedMs = Date.parse(telemetry.updated_at_utc);
  if (!Number.isFinite(updatedMs) || nowMs - updatedMs > STALE_AFTER_MS) return "STALE";
  if (runnerHealth !== "HEALTHY") return "DEGRADED";
  return "HEALTHY";
}

export function buildEquitySeries(telemetry: MonitoringTelemetry) {
  let equity = telemetry.initial_equity;
  let cumulativePnl = 0;
  const points = [{ label: "Start", equity, pnl: cumulativePnl }];
  for (const close of telemetry.closed_positions) {
    const pnl = close.realized_net_pnl;
    if (!isFiniteNumber(pnl)) continue;
    equity += pnl;
    cumulativePnl += pnl;
    const stamp = close.closed_at ?? "";
    points.push({
      label: stamp.length >= 16 ? stamp.slice(11, 16) : `#${points.length}`,
      equity: Number(equity.toFixed(10)),
      pnl: Number(cumulativePnl.toFixed(10)),
    });
  }
  return points;
}

export function buildMarkedEquitySeries(telemetry: MonitoringTelemetry) {
  if ((telemetry.schema_version !== V16_TELEMETRY_SCHEMA_VERSION && telemetry.schema_version !== V17_TELEMETRY_SCHEMA_VERSION && telemetry.schema_version !== V18_TELEMETRY_SCHEMA_VERSION && telemetry.schema_version !== V19_TELEMETRY_SCHEMA_VERSION && telemetry.schema_version !== V20_TELEMETRY_SCHEMA_VERSION && telemetry.schema_version !== V21_TELEMETRY_SCHEMA_VERSION) || !telemetry.account_history?.length) {
    return buildEquitySeries(telemetry);
  }
  return telemetry.account_history.map((point) => ({
    label: new Date(point.observed_at_ms).toISOString().slice(11, 16),
    equity: Number(point.marked_equity.toFixed(10)),
    pnl: Number((point.marked_equity - telemetry.initial_equity).toFixed(10)),
  }));
}

export function projectPositionScenario(
  position: PositionTelemetry,
  currentEquity: number,
  scenarioCapital: number,
  leverage: number,
) {
  const longNotional = position.long_entry_notional;
  const shortNotional = position.short_entry_notional;
  const netPnl = position.estimated_net_pnl_if_closed;
  if (
    position.mark_status !== "LIVE" ||
    !isFiniteNumber(longNotional) ||
    !isFiniteNumber(shortNotional) ||
    !isFiniteNumber(netPnl) ||
    !Number.isFinite(currentEquity) || currentEquity <= 0 ||
    !Number.isFinite(scenarioCapital) || scenarioCapital <= 0 ||
    !Number.isFinite(leverage) || leverage <= 0
  ) return null;

  const actualLeverage = isFiniteNumber(position.leverage) && position.leverage > 0 ? position.leverage : 1;
  const scale = (scenarioCapital / currentEquity) * (leverage / actualLeverage);
  const projectedLongNotional = longNotional * scale;
  const projectedShortNotional = shortNotional * scale;
  const grossExposure = projectedLongNotional + projectedShortNotional;
  const longInitialMargin = projectedLongNotional / leverage;
  const shortInitialMargin = projectedShortNotional / leverage;
  const initialMargin = longInitialMargin + shortInitialMargin;
  const estimatedNetPnl = netPnl * scale;

  return {
    scale,
    actual_leverage: actualLeverage,
    scenario_leverage: leverage,
    long_notional: projectedLongNotional,
    short_notional: projectedShortNotional,
    gross_exposure: grossExposure,
    long_initial_margin: longInitialMargin,
    short_initial_margin: shortInitialMargin,
    initial_margin: initialMargin,
    margin_pct_of_capital: initialMargin / scenarioCapital * 100,
    estimated_net_pnl_if_closed: estimatedNetPnl,
    pnl_pct_of_capital: estimatedNetPnl / scenarioCapital * 100,
    projected_account_value: scenarioCapital + estimatedNetPnl,
  };
}

export function projectOpportunityScenario(
  row: OpportunityRadarRow,
  capital: number,
  leverage: number,
  maxPositions = 6,
) {
  const modeledEdge = isFiniteNumber(row.expected_value_bps) ? row.expected_value_bps : row.best_net_edge_bps;
  if (row.signal_status !== "TRADEABLE" || !row.symbol || !row.buy_venue || !row.sell_venue || !isFiniteNumber(modeledEdge)) return null;
  const capacity = projectPortfolioCapacity(capital, leverage, maxPositions);
  if (!capacity) return null;
  return {
    symbol: row.symbol,
    long_exchange: row.buy_venue,
    short_exchange: row.sell_venue,
    leverage,
    long_notional: capacity.leg_notional_capacity,
    short_notional: capacity.leg_notional_capacity,
    gross_exposure: capacity.pair_gross_capacity,
    initial_margin: capacity.pair_initial_margin_capacity,
    best_net_edge_bps: modeledEdge,
  };
}

export function projectPortfolioCapacity(capital: number, leverage: number, maxPositions = 6) {
  if (!Number.isFinite(capital) || capital <= 0 || !Number.isFinite(leverage) || leverage <= 0) return null;
  if (!Number.isInteger(maxPositions) || maxPositions <= 0) return null;
  const gross = capital * leverage;
  const pairGross = gross / maxPositions;
  return {
    capital,
    leverage,
    max_positions: maxPositions,
    gross_capacity: gross,
    pair_gross_capacity: pairGross,
    leg_notional_capacity: pairGross / 2,
    total_initial_margin_capacity: gross / leverage,
    pair_initial_margin_capacity: pairGross / leverage,
  };
}
