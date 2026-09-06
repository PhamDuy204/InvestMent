from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from statistics import median, quantiles
from typing import Any, Iterable

from crypto_research.execution_v8 import ExecutionSimulatorV8
from crypto_research.stream_v18 import public_stream_health

PAYLOAD_SCHEMA_VERSION = "v13-monitoring-1"
V14_PAYLOAD_SCHEMA_VERSION = "v14-monitoring-1"
V15_PAYLOAD_SCHEMA_VERSION = "v15-monitoring-1"
V16_PAYLOAD_SCHEMA_VERSION = "v16-monitoring-1"
V17_PAYLOAD_SCHEMA_VERSION = "v17-monitoring-1"
V18_PAYLOAD_SCHEMA_VERSION = "v18-monitoring-1"
V19_PAYLOAD_SCHEMA_VERSION = "v19-monitoring-1"
V20_PAYLOAD_SCHEMA_VERSION = "v20-monitoring-1"
V21_PAYLOAD_SCHEMA_VERSION = "v21-monitoring-1"
V15_SHADOW_SCHEMA_VERSION = "v15-shadow-paper-1"
MAX_CLOSED_POSITIONS = 200

_V19_CANDIDATE_FUNNEL_KEYS = (
    "observed_route_occurrence",
    "feature_ready_occurrence",
    "ev_qualified_occurrence",
    "unique_candidate",
    "duplicate_rejected",
    "cooldown_rejected",
    "capacity_rejected",
    "margin_rejected",
    "depth_rejected",
    "reprice_ev_rejected",
    "pending_created",
    "no_causal_fill",
    "post_fill_rejected",
    "execution_abort",
    "paired_open",
)
_V21_PUBLIC_TRADE_VENUES = ("okx", "gate")
_V19_STREAM_ERROR_REASON_KEYS = (
    "KeyError",
    "TimeoutError",
    "ConnectionError",
    "OSError",
    "RuntimeError",
    "ValueError",
    "TypeError",
    "NetworkError",
    "ExchangeError",
    "RequestTimeout",
    "ExchangeNotAvailable",
    "DDoSProtection",
    "RateLimitExceeded",
    "InvalidNonce",
    "BadRequest",
    "BadSymbol",
    "NotSupported",
    "OperationFailed",
    "OperationRejected",
    "AuthenticationError",
    "Exception",
    "Other",
)

_OPEN_KEYS = (
    "position_id",
    "symbol",
    "long_exchange",
    "short_exchange",
    "quantity",
    "opened_at",
    "long_entry_vwap",
    "short_entry_vwap",
    "long_entry_notional",
    "short_entry_notional",
    "long_fee_bps",
    "short_fee_bps",
    "entry_fees",
    "initial_net_edge_bps",
    "strategy_id",
    "raw_net_edge_bps",
    "entry_baseline_bps",
    "entry_excess_spread_bps",
    "entry_excess_after_cost_bps",
    "entry_fee_hurdle_bps",
    "entry_z_score",
    "entry_route_sigma_bps",
    "entry_short_slope_bps_per_min",
    "entry_price_volatility_bps",
    "entry_expected_value_bps",
    "entry_minimum_ev_bps",
    "entry_capture_bps",
    "entry_baseline_15m_bps",
    "entry_baseline_5m_bps",
    "entry_fill_probability",
    "entry_execution_mode",
    "long_entry_liquidity",
    "short_entry_liquidity",
    "entry_hedge_delay_ms",
    "long_entry_fee_bps",
    "short_entry_fee_bps",
    "pair_gross_fraction",
    "margin_model",
    "leverage",
    "long_initial_margin",
    "short_initial_margin",
    "initial_margin",
    "entry_gross_exposure",
    "actual_gross_spread_bps",
    "actual_capture_bps",
    "post_fill_expected_value_bps",
    "post_fill_decision",
    "estimated_net_pnl_if_closed",
    "estimated_exit_fees",
    "long_current_vwap",
    "short_current_vwap",
    "long_unrealized_pnl",
    "short_unrealized_pnl",
    "gross_unrealized_pnl",
    "current_gross_exposure",
    "mark_status",
    "mark_updated_at_utc",
    "current_spread_bps",
    "held_seconds",
    "status",
)
_CLOSED_KEYS = (
    "position_id",
    "symbol",
    "long_exchange",
    "short_exchange",
    "quantity",
    "opened_at",
    "closed_at",
    "held_seconds",
    "close_reason",
    "long_entry_vwap",
    "short_entry_vwap",
    "long_exit_vwap",
    "short_exit_vwap",
    "entry_fees",
    "exit_fees",
    "gross_pnl",
    "realized_net_pnl",
    "initial_net_edge_bps",
    "remaining_spread_bps",
    "strategy_id",
    "raw_net_edge_bps",
    "entry_baseline_bps",
    "entry_excess_spread_bps",
    "entry_excess_after_cost_bps",
    "entry_fee_hurdle_bps",
    "entry_z_score",
    "entry_route_sigma_bps",
    "entry_short_slope_bps_per_min",
    "entry_price_volatility_bps",
    "pair_gross_fraction",
    "margin_model",
    "leverage",
    "long_initial_margin",
    "short_initial_margin",
    "initial_margin",
    "long_realized_net_pnl",
    "short_realized_net_pnl",
    "exit_execution_mode",
    "long_exit_liquidity",
    "short_exit_liquidity",
    "entry_expected_value_bps",
    "entry_capture_bps",
    "entry_execution_mode",
    "entry_hedge_delay_ms",
    "actual_gross_spread_bps",
    "actual_capture_bps",
    "post_fill_expected_value_bps",
    "post_fill_decision",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if isfinite(result) else default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pick(source: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def _sanitize_error(value: Any) -> str | None:
    if value in (None, ""):
        return None
    compact = " ".join(str(value).split())
    return compact[:240] or None


def _normalize_closed_positions(position_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    opens: dict[str, dict[str, Any]] = {}
    closed: list[dict[str, Any]] = []
    for event in position_events:
        if not isinstance(event, dict):
            continue
        position_id = str(event.get("position_id", ""))
        if not position_id:
            continue
        record_type = event.get("record_type")
        if record_type == "PAPER_POSITION_OPEN":
            opens[position_id] = event
            continue
        if record_type != "PAPER_POSITION_CLOSE":
            continue
        pnl_value = event.get("realized_net_pnl", event.get("net_pnl"))
        if pnl_value is None:
            continue
        merged = {**opens.get(position_id, {}), **event, "realized_net_pnl": _as_float(pnl_value)}
        closed.append(_pick(merged, _CLOSED_KEYS))
    return closed[-MAX_CLOSED_POSITIONS:]


def _max_drawdown_pct(initial_equity: float, closed_positions: list[dict[str, Any]]) -> float | None:
    if not closed_positions or initial_equity <= 0:
        return None
    equity = initial_equity
    peak = equity
    max_drawdown = 0.0
    for position in closed_positions:
        equity += _as_float(position.get("realized_net_pnl"))
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)
    return max_drawdown


def mark_open_position(
    position: dict[str, Any],
    *,
    long_book: dict[str, Any],
    short_book: dict[str, Any],
    marked_at_utc: str | None = None,
) -> dict[str, Any]:
    quantity = _as_float(position.get("quantity"))
    if quantity <= 0:
        return {"mark_status": "UNAVAILABLE", "margin_model": str(position.get("margin_model") or "NOT_MODELED")}

    long_fee_bps = _as_float(position.get("long_fee_bps"))
    short_fee_bps = _as_float(position.get("short_fee_bps"))
    try:
        long_fill = ExecutionSimulatorV8(fee_bps=long_fee_bps).simulate_market_order_by_quantity(
            target_base_quantity=quantity, side="sell", book=long_book
        )
        short_fill = ExecutionSimulatorV8(fee_bps=short_fee_bps).simulate_market_order_by_quantity(
            target_base_quantity=quantity, side="buy", book=short_book
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return {"mark_status": "UNAVAILABLE", "margin_model": str(position.get("margin_model") or "NOT_MODELED")}
    if long_fill.unmodeled_tail or short_fill.unmodeled_tail:
        return {"mark_status": "UNAVAILABLE", "margin_model": str(position.get("margin_model") or "NOT_MODELED")}

    long_entry = _as_float(position.get("long_entry_vwap"))
    short_entry = _as_float(position.get("short_entry_vwap"))
    entry_fees = _as_float(position.get("entry_fees"))
    long_pnl = quantity * (float(long_fill.vwap) - long_entry)
    short_pnl = quantity * (short_entry - float(short_fill.vwap))
    gross_pnl = long_pnl + short_pnl
    exit_fees = (
        float(long_fill.filled_notional) * long_fee_bps
        + float(short_fill.filled_notional) * short_fee_bps
    ) / 10_000.0
    midpoint = (float(long_fill.vwap) + float(short_fill.vwap)) / 2.0
    spread_bps = (
        (float(short_fill.vwap) - float(long_fill.vwap)) / midpoint * 10_000.0
        if midpoint > 0
        else 0.0
    )
    stamp = marked_at_utc or _now_utc()
    held_seconds = 0.0
    opened_at = position.get("opened_at")
    if isinstance(opened_at, str):
        try:
            held_seconds = max(0.0, (datetime.fromisoformat(stamp) - datetime.fromisoformat(opened_at)).total_seconds())
        except ValueError:
            held_seconds = 0.0

    entry_gross = _as_float(position.get("long_entry_notional")) + _as_float(
        position.get("short_entry_notional")
    )
    current_gross = float(long_fill.filled_notional) + float(short_fill.filled_notional)
    return {
        "mark_status": "LIVE",
        "mark_updated_at_utc": stamp,
        "long_current_vwap": float(long_fill.vwap),
        "short_current_vwap": float(short_fill.vwap),
        "long_unrealized_pnl": float(long_pnl),
        "short_unrealized_pnl": float(short_pnl),
        "gross_unrealized_pnl": float(gross_pnl),
        "estimated_exit_fees": float(exit_fees),
        "estimated_net_pnl_if_closed": float(gross_pnl - entry_fees - exit_fees),
        "current_spread_bps": float(spread_bps),
        "entry_gross_exposure": float(entry_gross),
        "current_gross_exposure": float(current_gross),
        "held_seconds": float(held_seconds),
        "margin_model": str(position.get("margin_model") or "NOT_MODELED"),
    }


def calculate_effectiveness(
    initial_equity: float,
    closed_positions: list[dict[str, Any]],
    scan_count: int,
) -> dict[str, Any]:
    del scan_count  # no trustworthy opportunity denominator exists in V13 state yet
    pnl = [_as_float(item.get("realized_net_pnl")) for item in closed_positions]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    total_fees = sum(
        _as_float(item.get("entry_fees")) + _as_float(item.get("exit_fees"))
        for item in closed_positions
    )
    hold_values = [
        _as_float(item.get("held_seconds"))
        for item in closed_positions
        if item.get("held_seconds") is not None
    ]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    count = len(pnl)

    return {
        "win_rate_pct": (len(wins) / count * 100.0) if count else None,
        "profit_factor": (gross_profit / gross_loss) if gross_profit > 0 and gross_loss > 0 else None,
        "avg_win": (sum(wins) / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "fee_drag": total_fees if count else None,
        "avg_holding_seconds": (sum(hold_values) / len(hold_values)) if hold_values else None,
        "max_drawdown_pct": _max_drawdown_pct(initial_equity, closed_positions),
        "opportunity_to_trade_pct": None,
        "closed_trade_count": count,
    }


def _event_timestamp(event: dict[str, Any]) -> datetime | None:
    for key in ("closed_at", "opened_at", "realized_at", "observed_at_utc", "updated_at_utc"):
        raw = event.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        try:
            stamp = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    return None


def _account_execution_summary(
    state: dict[str, Any],
    position_events: list[dict[str, Any]],
    *,
    updated_at_utc: str,
) -> dict[str, float | int | None]:
    """Reconcile account PnL from every journal event that mutates realized equity."""

    realized_pnl = _as_float(state.get("realized_pnl"))
    paired_pnl = 0.0
    non_paired_pnl = 0.0
    paired_fees = 0.0
    non_paired_fees = 0.0
    abort_count = 0
    abort_gross = 0.0
    abort_fees = 0.0
    abort_net = 0.0
    funding_pnl = 0.0
    timed_pnl: list[tuple[datetime, float]] = []
    entry_times: list[datetime] = []
    paired_count = 0

    for event in position_events:
        if not isinstance(event, dict):
            continue
        record_type = str(event.get("record_type") or "")
        stamp = _event_timestamp(event)
        if record_type == "PAPER_POSITION_OPEN":
            if stamp is not None:
                entry_times.append(stamp)
            continue
        if event.get("realized_net_pnl") is None:
            continue
        net = _as_float(event.get("realized_net_pnl"))
        fees = _as_float(event.get("entry_fees")) + _as_float(event.get("exit_fees"))
        if stamp is not None:
            timed_pnl.append((stamp, net))
        if record_type == "PAPER_POSITION_CLOSE":
            paired_count += 1
            paired_pnl += net
            paired_fees += fees
        else:
            non_paired_pnl += net
            non_paired_fees += fees
        if record_type == "PAPER_ONE_LEG_ABORT":
            abort_count += 1
            abort_gross += _as_float(event.get("gross_pnl"))
            abort_fees += fees
            abort_net += net
        if record_type == "PAPER_FUNDING_ACCRUAL":
            funding_pnl += net

    try:
        updated = datetime.fromisoformat(updated_at_utc)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        updated = updated.astimezone(timezone.utc)
    except ValueError:
        updated = datetime.now(timezone.utc)
    started_raw = state.get("started_at_utc")
    started: datetime | None = None
    if isinstance(started_raw, str) and started_raw:
        try:
            started = datetime.fromisoformat(started_raw)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            started = started.astimezone(timezone.utc)
        except ValueError:
            started = None
    runtime_hours = max(0.0, (updated - started).total_seconds() / 3600.0) if started else 0.0

    def rolling(hours: float) -> float:
        cutoff = updated.timestamp() - hours * 3600.0
        return sum(net for stamp, net in timed_pnl if stamp.timestamp() >= cutoff)

    entry_times.sort()
    gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(entry_times, entry_times[1:], strict=False)
        if later >= earlier
    ]
    median_gap = float(median(gaps)) if gaps else None
    p95_gap = (
        float(gaps[0])
        if len(gaps) == 1
        else float(quantiles(gaps, n=20, method="inclusive")[-1])
        if gaps
        else None
    )
    divisor = runtime_hours if runtime_hours > 0.0 else None
    return {
        "paired_realized_pnl": paired_pnl,
        "non_paired_execution_pnl": non_paired_pnl,
        "account_pnl_reconciliation_error": realized_pnl - paired_pnl - non_paired_pnl,
        "abort_count": abort_count,
        "abort_gross_pnl": abort_gross,
        "abort_fees": abort_fees,
        "abort_net_pnl": abort_net,
        "realized_funding_pnl": funding_pnl,
        "paired_fee_drag": paired_fees,
        "non_paired_fee_drag": non_paired_fees,
        "total_fee_drag": paired_fees + non_paired_fees,
        "runtime_hours": runtime_hours,
        "paired_trades_per_hour": paired_count / divisor if divisor else 0.0,
        "paired_pnl_per_hour": paired_pnl / divisor if divisor else 0.0,
        "account_pnl_per_hour": realized_pnl / divisor if divisor else 0.0,
        "abort_count_per_hour": abort_count / divisor if divisor else 0.0,
        "abort_loss_per_hour": abort_net / divisor if divisor else 0.0,
        "funding_pnl_per_hour": funding_pnl / divisor if divisor else 0.0,
        "rolling_1h_pnl": rolling(1.0),
        "rolling_3h_pnl": rolling(3.0),
        "rolling_6h_pnl": rolling(6.0),
        "median_entry_gap_seconds": median_gap,
        "p95_entry_gap_seconds": p95_gap,
    }


_RADAR_KEYS = (
    "symbol",
    "venue_count",
    "decision",
    "buy_venue",
    "sell_venue",
    "gross_edge_bps",
    "total_fee_bps",
    "safety_buffer_bps",
    "best_net_edge_bps",
    "signal_status",
    "edge_to_trade_bps",
    "optimizer_score_bps",
    "optimizer_rank",
    "baseline_bps",
    "route_sigma_bps",
    "excess_spread_bps",
    "fee_hurdle_bps",
    "excess_after_cost_bps",
    "z_score",
    "short_slope_bps_per_min",
    "medium_slope_bps_per_min",
    "price_volatility_bps",
    "history_sample_count",
    "history_span_seconds",
    "proposed_leverage",
    "proposed_pair_gross_fraction",
    "proposed_target_notional",
    "baseline_60m_bps",
    "baseline_15m_bps",
    "baseline_5m_bps",
    "structural_excess_bps",
    "local_excess_bps",
    "fast_excess_bps",
    "capture_bps",
    "expected_value_bps",
    "minimum_required_ev_bps",
    "p_open",
    "p_one_leg",
    "long_fill_probability",
    "short_fill_probability",
    "long_exit_fill_probability",
    "short_exit_fill_probability",
    "expected_entry_fee_bps",
    "expected_exit_fee_bps",
    "adverse_selection_bps",
    "hedge_risk_bps",
    "four_taker_hurdle_bps",
    "maker_round_trip_hurdle_bps",
    "long_quote_spread_bps",
    "short_quote_spread_bps",
    "expected_entry_price_improvement_bps",
    "expected_exit_price_improvement_bps",
    "persistence_sample_count",
    "persistence_seconds",
    "spread_slope_bps_per_min",
    "funding_status",
    "funding_edge_bps",
    "maker_side",
    "maker_venue",
    "hedge_venue",
    "post_fill_accept_probability",
    "estimated_accept_probability",
    "reject_net_bps",
    "expected_attempt_ev_bps",
    "conditional_pair_value_bps",
    "max_conditional_pair_value_bps",
    "conditional_fill_value_bps",
    "execution_calibration_global_fills",
    "execution_calibration_local_fills",
)


def _sanitize_number_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, float] = {}
    for key, raw in value.items():
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if isfinite(number):
            output[str(key)[:80]] = number
    return output


def _sanitize_bounded_count_map(
    value: Any,
    allowed_keys: tuple[str, ...],
    *,
    include_missing: bool = False,
) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    output: dict[str, int] = {}
    for key in allowed_keys:
        raw = source.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(float(raw)):
            if include_missing:
                output[key] = 0
            continue
        output[key] = max(0, int(raw))
    return output


def _sanitize_stream_error_counts_by_venue(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, dict[str, int]] = {}
    for raw_venue, raw_counts in list(value.items())[:32]:
        venue = str(raw_venue)[:64]
        if not venue:
            continue
        counts = _sanitize_bounded_count_map(
            raw_counts,
            _V19_STREAM_ERROR_REASON_KEYS,
        )
        if counts:
            output[venue] = counts
    return output


def _sanitize_radar(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for raw in value[:100]:
        if not isinstance(raw, dict):
            continue
        row = _pick(raw, _RADAR_KEYS)
        for key, field in list(row.items()):
            if isinstance(field, (int, float)) and not isfinite(float(field)):
                row.pop(key)
        venues = raw.get("available_venues")
        if isinstance(venues, list):
            row["available_venues"] = [str(item)[:80] for item in venues[:10]]
        rows.append(row)
    return rows



_V15_STRATEGY_IDS = (
    "CONTROL_V14C",
    "ADAPTIVE_EXIT_SHADOW_V1",
    "SPREAD_CONTINUATION_SHADOW_V1",
    "FUNDING_AWARE_SHADOW_V1",
)
_V15_STRATEGY_KEYS = (
    "strategy_id",
    "mode",
    "open_position_count",
    "closed_trade_count",
    "realized_pnl",
    "win_rate_pct",
    "profit_factor",
    "observed_route_count",
)
_V15_DIAGNOSTIC_KEYS = (
    "persistence_sample_count",
    "persistence_seconds",
    "spread_slope_bps_per_min",
    "funding_status",
    "funding_edge_bps",
    "maker_side",
    "maker_venue",
    "hedge_venue",
    "post_fill_accept_probability",
    "estimated_accept_probability",
    "reject_net_bps",
    "expected_attempt_ev_bps",
    "conditional_pair_value_bps",
    "max_conditional_pair_value_bps",
    "conditional_fill_value_bps",
    "execution_calibration_global_fills",
    "execution_calibration_local_fills",
)


def _sanitize_strategy_lab(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    output: list[dict[str, Any]] = []
    for strategy_id in _V15_STRATEGY_IDS:
        raw = value.get(strategy_id)
        if not isinstance(raw, dict) or raw.get("strategy_id") != strategy_id:
            continue
        row = _pick(raw, _V15_STRATEGY_KEYS)
        if row.get("profit_factor") is not None and not isinstance(row.get("profit_factor"), (int, float)):
            row.pop("profit_factor", None)
        if row.get("win_rate_pct") is not None and not isinstance(row.get("win_rate_pct"), (int, float)):
            row.pop("win_rate_pct", None)
        output.append(row)
    return output


def _merge_v15_radar_diagnostics(
    radar: list[dict[str, Any]],
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return radar
    for row in radar:
        symbol = str(row.get("symbol") or "")
        buy = str(row.get("buy_venue") or "")
        sell = str(row.get("sell_venue") or "")
        raw = value.get(symbol)
        if not isinstance(raw, dict) or raw.get("route") != f"{buy}->{sell}":
            continue
        for key in _V15_DIAGNOSTIC_KEYS:
            field = raw.get(key)
            if isinstance(field, str) or (isinstance(field, (int, float)) and isfinite(float(field))):
                row[key] = field
    return radar

_V17_PENDING_ENTRY_KEYS = (
    "pending_id",
    "symbol",
    "long_exchange",
    "short_exchange",
    "quantity",
    "placed_at_utc",
    "status",
    "long_limit_price",
    "short_limit_price",
    "expected_value_bps",
    "minimum_required_ev_bps",
    "capture_bps",
    "p_open",
    "leverage",
    "pair_gross_fraction",
    "actual_gross_spread_bps",
    "actual_capture_bps",
    "post_fill_expected_value_bps",
    "post_fill_decision",
)
_V19_PENDING_ENTRY_KEYS = (
    *_V17_PENDING_ENTRY_KEYS,
    "filled_side",
    "filled_venue",
    "cancelled_maker_leg",
    "unwind_reason",
    "unwind_pending_since_utc",
    "partial_entry_price",
    "partial_entry_notional",
    "partial_entry_fee_bps",
    "partial_entry_fee",
    "partial_gross_notional",
    "partial_gross_unrealized_pnl",
    "partial_unrealized_pnl",
    "partial_initial_margin",
    "partial_mark_status",
    "partial_current_vwap",
    "partial_estimated_exit_fee",
    "partial_estimated_net_pnl_if_unwound",
    "unwind_attempt_count",
    "unwind_failure_count",
    "maker_side",
)
_V17_PENDING_EXIT_KEYS = (
    "pending_id",
    "position_id",
    "symbol",
    "long_exchange",
    "short_exchange",
    "quantity",
    "placed_at_utc",
    "status",
    "long_limit_price",
    "short_limit_price",
    "reason",
)


def _sanitize_pending(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for raw in value[:32]:
        if not isinstance(raw, dict):
            continue
        row = _pick(raw, keys)
        for key, field in list(row.items()):
            if isinstance(field, (int, float)) and not isfinite(float(field)):
                row.pop(key)
        output.append(row)
    return output


_V16_ACCOUNT_HISTORY_KEYS = (
    "observed_at_ms",
    "realized_equity",
    "marked_equity",
    "realized_pnl",
    "unrealized_net_pnl",
    "gross_exposure",
    "margin_used",
    "modeled_fee_drag",
)
_V16_POSITION_HISTORY_KEYS = (
    "observed_at_ms",
    "symbol",
    "spread_bps",
    "net_pnl",
    "baseline_bps",
)


def _sanitize_v16_monitor_history(value: Any) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    if not isinstance(value, dict):
        return [], {}
    account_output: list[dict[str, Any]] = []
    raw_account = value.get("account_history")
    if isinstance(raw_account, list):
        for raw in raw_account[-360:]:
            if not isinstance(raw, dict):
                continue
            row = _pick(raw, _V16_ACCOUNT_HISTORY_KEYS)
            if all(isinstance(field, (int, float)) and isfinite(float(field)) for field in row.values()):
                account_output.append(row)

    position_output: dict[str, list[dict[str, Any]]] = {}
    raw_positions = value.get("position_history")
    if isinstance(raw_positions, dict):
        for position_id, samples in list(raw_positions.items())[:64]:
            if not isinstance(position_id, str) or not position_id or not isinstance(samples, list):
                continue
            clean_samples: list[dict[str, Any]] = []
            for raw in samples[-120:]:
                if not isinstance(raw, dict):
                    continue
                row = _pick(raw, _V16_POSITION_HISTORY_KEYS)
                symbol = row.get("symbol")
                numeric = [field for key, field in row.items() if key != "symbol"]
                if not isinstance(symbol, str) or not symbol:
                    continue
                if not all(isinstance(field, (int, float)) and isfinite(float(field)) for field in numeric):
                    continue
                clean_samples.append(row)
            if clean_samples:
                position_output[position_id[:128]] = clean_samples
    return account_output, position_output


def build_monitoring_payload(
    state: dict[str, Any],
    health: dict[str, Any],
    position_events: list[dict[str, Any]],
    *,
    shadow_state: dict[str, Any] | None = None,
    monitor_history: dict[str, Any] | None = None,
    updated_at_utc: str | None = None,
) -> dict[str, Any]:
    initial_equity = _as_float(state.get("initial_equity"), 0.0)
    equity = _as_float(state.get("equity"), initial_equity)
    realized_pnl = _as_float(state.get("realized_pnl"), equity - initial_equity)
    return_pct = ((equity - initial_equity) / initial_equity * 100.0) if initial_equity else 0.0
    raw_open_positions = state.get("open_positions") or []
    open_positions = [
        _pick(position, _OPEN_KEYS)
        for position in raw_open_positions
        if isinstance(position, dict)
    ]
    closed_positions = _normalize_closed_positions(position_events)
    scan_count = _as_int(state.get("scan_count"))

    state_schema = state.get("schema_version")
    is_v14 = state_schema == "v14-arbitrage-paper-1"
    is_v16 = state_schema == "v16-arbitrage-paper-1"
    is_v17 = state_schema == "v17-arbitrage-paper-1"
    is_v18 = state_schema == "v18-arbitrage-paper-1"
    is_v19 = state_schema == "v19-arbitrage-paper-1"
    is_v20 = state_schema == "v20-arbitrage-paper-1"
    is_v21 = state_schema == "v21-arbitrage-paper-1"
    is_cross_margin = is_v14 or is_v16 or is_v17 or is_v18 or is_v19 or is_v20 or is_v21
    payload_schema = (
        V21_PAYLOAD_SCHEMA_VERSION
        if is_v21
        else V20_PAYLOAD_SCHEMA_VERSION
        if is_v20
        else V19_PAYLOAD_SCHEMA_VERSION
        if is_v19
        else V18_PAYLOAD_SCHEMA_VERSION
        if is_v18
        else V17_PAYLOAD_SCHEMA_VERSION
        if is_v17
        else V16_PAYLOAD_SCHEMA_VERSION
        if is_v16
        else V14_PAYLOAD_SCHEMA_VERSION
        if is_v14
        else PAYLOAD_SCHEMA_VERSION
    )
    payload_updated_at = updated_at_utc or _now_utc()
    runner_health = str(health.get("status") or "UNKNOWN").upper()
    runner_error = health.get("error")
    if runner_health == "HEALTHY":
        runner_health, coverage_error = public_stream_health(state)
        runner_error = coverage_error or runner_error
    heartbeat = health.get("updated_at_utc")
    if runner_health in {"HEALTHY", "DEGRADED"} and isinstance(heartbeat, str):
        try:
            heartbeat_age = (
                datetime.fromisoformat(payload_updated_at) - datetime.fromisoformat(heartbeat)
            ).total_seconds()
            stale_after_seconds = 120.0 if is_v20 or is_v21 else 15.0
            if heartbeat_age > stale_after_seconds:
                runner_health = "STALE"
        except ValueError:
            pass
    payload = {
        "schema_version": payload_schema,
        "updated_at_utc": payload_updated_at,
        "runner_health": runner_health,
        "runner_error": _sanitize_error(runner_error),
        "initial_equity": initial_equity,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "return_pct": return_pct,
        "scan_count": scan_count,
        "opened_position_count": _as_int(state.get("opened_position_count")),
        "closed_position_count": _as_int(state.get("closed_position_count")),
        "open_position_count": len(open_positions),
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "metrics": calculate_effectiveness(initial_equity, closed_positions, scan_count),
    }
    if is_cross_margin:
        universe = state.get("universe_symbols")
        payload.update(
            {
                "margin_model": str(state.get("margin_model") or "UNKNOWN"),
                "portfolio_model": str(state.get("portfolio_model") or ""),
                "maintenance_stress_rate": _as_float(state.get("maintenance_stress_rate")),
                "margin_utilization_cap": _as_float(state.get("margin_utilization_cap")),
                "venue_concentration_penalty_bps": _as_float(state.get("venue_concentration_penalty_bps")),
                "maintenance_stress_used": _as_float(state.get("maintenance_stress_used")),
                "min_stress_margin_ratio": (
                    _as_float(state.get("min_stress_margin_ratio"))
                    if state.get("min_stress_margin_ratio") is not None
                    else None
                ),
                "exchange_leverage": _as_float(state.get("exchange_leverage")),
                "gross_leverage_cap": _as_float(state.get("gross_leverage_cap")),
                "gross_leverage_used": _as_float(state.get("gross_leverage_used")),
                "gross_exposure": _as_float(state.get("gross_exposure")),
                "initial_margin_used": _as_float(state.get("initial_margin_used")),
                "available_margin": _as_float(state.get("available_margin")),
                "max_open_positions": _as_int(state.get("max_open_positions")),
                "single_pair_gross_fraction": _as_float(state.get("single_pair_gross_fraction")),
                "qualified_opportunity_count": _as_int(state.get("qualified_opportunity_count")),
                "observed_signal_count": _as_int(state.get("observed_signal_count")),
                "last_cycle_signal_count": _as_int(state.get("last_cycle_signal_count")),
                "last_cycle_tradeable_count": _as_int(state.get("last_cycle_tradeable_count")),
                "venue_balances": _sanitize_number_map(state.get("venue_balances")),
                "venue_margin_used": _sanitize_number_map(state.get("venue_margin_used")),
                "venue_available_margin": _sanitize_number_map(state.get("venue_available_margin")),
                "venue_account_equity": _sanitize_number_map(state.get("venue_account_equity")),
                "venue_unrealized_pnl": _sanitize_number_map(state.get("venue_unrealized_pnl")),
                "venue_maintenance_stress": _sanitize_number_map(state.get("venue_maintenance_stress")),
                "venue_margin_ratio": _sanitize_number_map(state.get("venue_margin_ratio")),
                "venue_margin_utilization": _sanitize_number_map(state.get("venue_margin_utilization")),
                "universe_size": len(universe) if isinstance(universe, list) else 0,
                "opportunity_radar": _sanitize_radar(state.get("opportunity_radar")),
                "invariant_failure_count": _as_int(state.get("invariant_failure_count")),
                "started_at_utc": str(state.get("started_at_utc") or ""),
            }
        )
    if is_v16 or is_v17 or is_v18 or is_v19 or is_v20 or is_v21:
        account_history, position_history = _sanitize_v16_monitor_history(monitor_history)
        payload["account_history"] = account_history
        payload["position_history"] = position_history
    if is_v17 or is_v18 or is_v19 or is_v20 or is_v21:
        pending_entry_keys = (
            _V19_PENDING_ENTRY_KEYS if (is_v19 or is_v20 or is_v21) else _V17_PENDING_ENTRY_KEYS
        )
        pending_entries = _sanitize_pending(
            state.get("pending_entries"), pending_entry_keys
        )
        pending_exits = _sanitize_pending(state.get("pending_exits"), _V17_PENDING_EXIT_KEYS)
        payload.update(
            {
                "pending_entry_count": len(pending_entries),
                "pending_exit_count": len(pending_exits),
                "pending_entries": pending_entries,
                "pending_exits": pending_exits,
                "maker_probe_count": _as_int(state.get("maker_probe_count")),
                "maker_fill_observation_count": _as_int(state.get("maker_fill_observation_count")),
                "maker_entry_cancel_count": _as_int(state.get("maker_entry_cancel_count")),
                "one_leg_hedge_count": _as_int(state.get("one_leg_hedge_count")),
                "maker_exit_fallback_count": _as_int(state.get("maker_exit_fallback_count")),
                "maker_hedge_failure_count": _as_int(state.get("maker_hedge_failure_count")),
            }
        )
    if is_v18 or is_v19 or is_v20 or is_v21:
        payload.update(
            {
                "post_fill_accept_count": _as_int(state.get("post_fill_accept_count")),
                "post_fill_reject_count": _as_int(state.get("post_fill_reject_count")),
                "both_maker_fill_count": _as_int(state.get("both_maker_fill_count")),
                "one_leg_abort_count": _as_int(state.get("one_leg_abort_count")),
                "one_leg_abort_pnl": _as_float(state.get("one_leg_abort_pnl")),
                "book_update_count": _as_int(state.get("book_update_count")),
                "ws_reconnect_count": _as_int(state.get("ws_reconnect_count")),
                "book_cache_entry_count": _as_int(state.get("book_cache_entry_count")),
                "fresh_book_count": _as_int(state.get("fresh_book_count")),
                "stale_book_count": _as_int(state.get("stale_book_count")),
                "connected_venue_count": _as_int(state.get("connected_venue_count")),
                "expected_venue_count": _as_int(state.get("expected_venue_count")),
                "book_age_ms_median": (
                    _as_float(state.get("book_age_ms_median"))
                    if state.get("book_age_ms_median") is not None
                    else None
                ),
                "book_age_ms_max": (
                    _as_float(state.get("book_age_ms_max"))
                    if state.get("book_age_ms_max") is not None
                    else None
                ),
                "memory_prune_count": _as_int(state.get("memory_prune_count")),
                "process_rss_bytes": _as_int(state.get("process_rss_bytes")),
            }
        )
    if is_v21:
        payload.update(
            {
                "target_realized_pnl_per_hour": _as_float(state.get("target_realized_pnl_per_hour")),
                "funding_refresh_age_seconds": (
                    max(0.0, datetime.fromisoformat(payload_updated_at).timestamp()
                        - _as_float(state.get("funding_last_full_refresh_ms")) / 1000.0)
                    if _as_float(state.get("funding_last_full_refresh_ms")) > 0 else None
                ),
                "stream_errors_last_60s_by_venue": _sanitize_bounded_count_map(
                    state.get("stream_errors_last_60s_by_venue"),
                    ("binance", "bybit", "bitget", "okx", "gate", "kucoin", "mexc"),
                ),
                "v21_shadow_accept_count": _as_int(state.get("v21_shadow_accept_count")),
                "v21_shadow_reject_count": _as_int(state.get("v21_shadow_reject_count")),
                "public_trade_update_count": _as_int(state.get("public_trade_update_count")),
                "public_trade_update_counts_by_venue": _sanitize_bounded_count_map(
                    state.get("public_trade_update_counts_by_venue"),
                    _V21_PUBLIC_TRADE_VENUES,
                    include_missing=True,
                ),
            }
        )
    if is_v19 or is_v20 or is_v21:
        payload.update(
            {
                "age_expired_book_count": _as_int(state.get("age_expired_book_count")),
                "skew_rejected_book_count": _as_int(state.get("skew_rejected_book_count")),
                "disconnected_book_count": _as_int(state.get("disconnected_book_count")),
                "one_leg_unwind_attempt_count": _as_int(
                    state.get("one_leg_unwind_attempt_count")
                ),
                "one_leg_unwind_failure_count": _as_int(
                    state.get("one_leg_unwind_failure_count")
                ),
                "partial_exposure_count": _as_int(
                    state.get("partial_exposure_count")
                ),
                "partial_exposure_gross_notional": _as_float(
                    state.get("partial_exposure_gross_notional")
                ),
                "partial_exposure_unrealized_pnl": _as_float(
                    state.get("partial_exposure_unrealized_pnl")
                ),
                "partial_exposure_entry_fees": _as_float(
                    state.get("partial_exposure_entry_fees")
                ),
                "partial_exposure_reserved_margin": _as_float(
                    state.get("partial_exposure_reserved_margin")
                ),
                "candidate_funnel_counts": _sanitize_bounded_count_map(
                    state.get("candidate_funnel_counts"),
                    _V19_CANDIDATE_FUNNEL_KEYS,
                    include_missing=True,
                ),
                "stream_error_counts": _sanitize_bounded_count_map(
                    state.get("stream_error_counts"),
                    _V19_STREAM_ERROR_REASON_KEYS,
                ),
                "stream_error_counts_by_venue": _sanitize_stream_error_counts_by_venue(
                    state.get("stream_error_counts_by_venue")
                ),
            }
        )

    if is_v20 or is_v21:
        payload.update(
            _account_execution_summary(
                state,
                position_events,
                updated_at_utc=payload_updated_at,
            )
        )

    if (
        is_v14
        and isinstance(shadow_state, dict)
        and shadow_state.get("schema_version") == V15_SHADOW_SCHEMA_VERSION
    ):
        payload["schema_version"] = V15_PAYLOAD_SCHEMA_VERSION
        payload["shadow_updated_at_utc"] = str(shadow_state.get("updated_at_utc") or "")
        payload["strategy_lab"] = _sanitize_strategy_lab(shadow_state.get("strategy_lab"))
        payload["opportunity_radar"] = _merge_v15_radar_diagnostics(
            payload.get("opportunity_radar", []),
            shadow_state.get("radar_diagnostics"),
        )
    return payload
