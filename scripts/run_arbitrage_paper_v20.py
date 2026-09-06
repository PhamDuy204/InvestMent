"""V20 execution-aware single-maker public-data paper arbitrage."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from crypto_research.arbitrage_v12 import ArbitrageOpportunity, VenueBook
from crypto_research.funding_v20 import (
    accrue_deribit_funding_cashflow,
    accrue_discrete_funding_cashflow,
    pair_funding_admission,
)
from crypto_research.maker_v17 import (
    conservative_fill_probability,
    multi_horizon_route_features,
    passive_limit_filled,
)
from crypto_research.maker_v18 import post_fill_entry_ev
from crypto_research.maker_v20 import (
    record_v20_execution_outcome,
    single_maker_attempt_ev,
    v20_execution_calibration,
)

if __package__:
    from .run_arbitrage_paper_v17 import (
        _append_jsonl,
        _market_fill,
        _process_maker_probes,
        _quote_spread_bps,
    )
    from .run_arbitrage_paper_v19 import _process_pending_entries_v19
else:
    from run_arbitrage_paper_v17 import (
        _append_jsonl,
        _market_fill,
        _process_maker_probes,
        _quote_spread_bps,
    )
    from run_arbitrage_paper_v19 import _process_pending_entries_v19


SCHEMA_VERSION = "v20-arbitrage-paper-1"
HEALTH_SCHEMA_VERSION = "v20-arbitrage-health-1"
PORTFOLIO_MODEL = "WS_EXECUTION_AWARE_SINGLE_MAKER_V1"
STRATEGY_ID = PORTFOLIO_MODEL
TARGET_ACCOUNT_PNL_PER_HOUR = 0.05
PENDING_ENTRY_TIMEOUT_SECONDS = 30.0


def _v20_route_decision(
    opportunity: ArbitrageOpportunity,
    *,
    features: dict[str, float | int] | None,
    stats_db: str | Path,
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    safety_buffer_bps: float,
    venues: dict[str, VenueBook] | None = None,
    funding_snapshots: dict[str, dict[str, Any]] | None = None,
    now_ms: int | None = None,
    attempt_capacity_per_hour: float = 240.0,
    max_hold_seconds: float = 65.0 * 60.0,
    price_discrete_funding: bool = False,
    calibration_provider: Any = None,
    attempt_ev_function: Any = None,
) -> dict[str, Any]:
    """Choose one maker side by conservative account-level terminal EV."""

    if features is None:
        return {"decision": "BASELINE_WARMUP", "tradeable": False}
    if venues is None:
        raise ValueError("V20 route decision requires executable venue books")
    if now_ms is None:
        raise ValueError("V20 route decision requires now_ms for funding causality")
    snapshots = funding_snapshots or {}
    funding = pair_funding_admission(
        long_venue=opportunity.buy_venue,
        short_venue=opportunity.sell_venue,
        long_snapshot=snapshots.get(f"{opportunity.buy_venue}|{opportunity.symbol}"),
        short_snapshot=snapshots.get(f"{opportunity.sell_venue}|{opportunity.symbol}"),
        now_ms=int(now_ms),
        max_hold_seconds=float(max_hold_seconds),
        price_discrete_funding=price_discrete_funding,
    )
    if funding["blocked"]:
        return {
            "decision": str(funding["reason"]),
            "tradeable": False,
            "funding_ready": bool(funding["ready"]),
            "expected_funding_cost_bps": float(funding["expected_funding_cost_bps"]),
            "expected_net_funding_cost_bps": float(funding["expected_net_funding_cost_bps"]),
        }

    current = float(opportunity.gross_edge_bps)
    baseline_60 = float(features["baseline_60m_bps"])
    baseline_15 = float(features["baseline_15m_bps"])
    baseline_5 = float(features["baseline_5m_bps"])
    excess_60 = current - baseline_60
    excess_15 = current - baseline_15
    excess_5 = current - baseline_5
    capture = max(0.0, min(excess_60, excess_15))
    sigma = max(0.5, float(features["route_sigma_bps"]))
    volatility = max(0.0, float(features["price_volatility_bps"]))
    long_quote_spread = _quote_spread_bps(venues[opportunity.buy_venue])
    short_quote_spread = _quote_spread_bps(venues[opportunity.sell_venue])

    long_fill = conservative_fill_probability(stats_db, opportunity.buy_venue, "buy")
    short_fill = conservative_fill_probability(stats_db, opportunity.sell_venue, "sell")
    if calibration_provider is None:
        def calibration_provider(db_path: str | Path, *, venue: str, side: str, placement_capture_bps: float) -> dict[str, Any]:
            del placement_capture_bps
            return v20_execution_calibration(db_path, venue=venue, side=side)
    if attempt_ev_function is None:
        attempt_ev_function = single_maker_attempt_ev
    long_calibration = calibration_provider(
        stats_db,
        venue=opportunity.buy_venue,
        side="LONG",
        placement_capture_bps=capture,
    )
    short_calibration = calibration_provider(
        stats_db,
        venue=opportunity.sell_venue,
        side="SHORT",
        placement_capture_bps=capture,
    )

    # V19's profitable close path uses executable taker snapshots. Until V20 has
    # enough exit-specific evidence, admission grants no future maker-exit saving.
    exit_fee_bps = float(taker_fee_bps[opportunity.buy_venue]) + float(
        taker_fee_bps[opportunity.sell_venue]
    )
    adverse_selection_bps = max(0.25, 0.10 * sigma + 0.05 * volatility)
    if not math.isfinite(float(attempt_capacity_per_hour)) or float(attempt_capacity_per_hour) <= 0.0:
        raise ValueError("attempt_capacity_per_hour must be finite and positive")
    minimum_attempt_dollars_objective = TARGET_ACCOUNT_PNL_PER_HOUR / float(attempt_capacity_per_hour)
    objective_floor_bps = minimum_attempt_dollars_objective / max(1e-9, float(opportunity.target_notional)) * 10_000.0
    risk_floor_bps = max(0.25, 0.05 * sigma + 0.02 * volatility)
    minimum_attempt_ev_bps = max(risk_floor_bps, objective_floor_bps)

    actions: list[dict[str, Any]] = []
    for side, maker_venue, hedge_venue, fill, calibration, quote_improvement in (
        (
            "LONG",
            opportunity.buy_venue,
            opportunity.sell_venue,
            long_fill,
            long_calibration,
            long_quote_spread,
        ),
        (
            "SHORT",
            opportunity.sell_venue,
            opportunity.buy_venue,
            short_fill,
            short_calibration,
            short_quote_spread,
        ),
    ):
        ev = attempt_ev_function(
            pair_capture_bps=capture,
            maker_fee_bps=float(maker_fee_bps[maker_venue]),
            hedge_taker_fee_bps=float(taker_fee_bps[hedge_venue]),
            expected_exit_fee_bps=exit_fee_bps,
            expected_exit_price_improvement_bps=0.0,
            maker_quote_improvement_bps=float(quote_improvement),
            adverse_selection_bps=adverse_selection_bps,
            safety_buffer_bps=float(safety_buffer_bps),
            expected_funding_cost_bps=float(funding["expected_funding_cost_bps"]),
            fill_probability=float(fill["conservative_probability"]),
            minimum_attempt_ev_bps=minimum_attempt_ev_bps,
            calibration=calibration,
        )
        actions.append(
            {
                "maker_side": side,
                "maker_venue": maker_venue,
                "hedge_venue": hedge_venue,
                "fill_probability": float(fill["conservative_probability"]),
                "fill_attempts": int(fill["attempts"]),
                "fill_count": int(fill["fills"]),
                "calibration": calibration,
                **ev,
            }
        )

    selected = max(actions, key=lambda row: float(row["expected_attempt_ev_bps"]))
    selected_calibration = selected["calibration"]
    decision: dict[str, Any] = {
        "baseline_60m_bps": baseline_60,
        "baseline_15m_bps": baseline_15,
        "baseline_5m_bps": baseline_5,
        "route_sigma_bps": sigma,
        "price_volatility_bps": volatility,
        "structural_excess_bps": excess_60,
        "local_excess_bps": excess_15,
        "fast_excess_bps": excess_5,
        "capture_bps": capture,
        "z_score": capture / sigma,
        "long_quote_spread_bps": long_quote_spread,
        "short_quote_spread_bps": short_quote_spread,
        "long_fill_probability": float(long_fill["conservative_probability"]),
        "short_fill_probability": float(short_fill["conservative_probability"]),
        "expected_exit_fee_bps": exit_fee_bps,
        "expected_exit_price_improvement_bps": 0.0,
        "adverse_selection_bps": adverse_selection_bps,
        "funding_ready": True,
        "funding_decision": str(funding["reason"]),
        "expected_funding_cost_bps": float(funding["expected_funding_cost_bps"]),
        "expected_net_funding_cost_bps": float(funding["expected_net_funding_cost_bps"]),
        "maker_side": str(selected["maker_side"]),
        "maker_venue": str(selected["maker_venue"]),
        "hedge_venue": str(selected["hedge_venue"]),
        "p_open": float(selected["fill_probability"]),
        "post_fill_accept_probability": float(
            selected["post_fill_accept_probability"]
        ),
        "reject_net_bps": float(selected["reject_net_bps"]),
        "expected_attempt_ev_bps": float(selected["expected_attempt_ev_bps"]),
        "expected_attempt_dollars": float(selected["expected_attempt_ev_bps"]) / 10_000.0 * float(opportunity.target_notional),
        "minimum_required_attempt_dollars": minimum_attempt_ev_bps / 10_000.0 * float(opportunity.target_notional),
        "minimum_hourly_target_share_dollars": minimum_attempt_dollars_objective,
        "attempt_capacity_per_hour": float(attempt_capacity_per_hour),
        "conditional_pair_value_bps": float(selected["conditional_pair_value_bps"]),
        "max_conditional_pair_value_bps": max(float(action["conditional_pair_value_bps"]) for action in actions),
        "conditional_fill_value_bps": float(selected["conditional_fill_value_bps"]),
        "estimated_accept_probability": float(
            selected_calibration.get(
                "estimated_accept_probability",
                selected["post_fill_accept_probability"],
            )
        ),
        "expected_value_bps": float(selected["expected_attempt_ev_bps"]),
        "minimum_required_ev_bps": float(
            selected["minimum_required_attempt_ev_bps"]
        ),
        "execution_calibration_global_fills": int(
            selected_calibration["global_fill_count"]
        ),
        "execution_calibration_local_fills": int(
            selected_calibration["local_fill_count"]
        ),
    }

    if capture <= 0.0:
        decision.update({"decision": "NO_ROUTE_DISLOCATION", "tradeable": False})
    else:
        decision.update(
            {
                "decision": str(selected["decision"]),
                "tradeable": bool(selected["tradeable"]),
            }
        )
    return decision


def _snapshot_future_funding_timestamp(snapshot: dict[str, Any], *, now_ms: int) -> int | None:
    for key in ("fundingTimestamp", "nextFundingTimestamp"):
        try:
            stamp = int(snapshot.get(key))
        except (TypeError, ValueError):
            continue
        if stamp > int(now_ms):
            return stamp
    return None


def _seed_new_position_funding_state(
    state: dict[str, Any],
    *,
    previous_position_ids: set[str],
) -> None:
    """Pin causal funding rate/mark/schedule onto newly opened V20 positions."""

    snapshots = state.get("funding_snapshots", {})
    for position in state.get("open_positions", []):
        if str(position.get("position_id") or "") in previous_position_ids:
            continue
        symbol = str(position.get("symbol") or "")
        opened_at_ms = int(position.get("opened_at_ms", 0) or 0)
        for prefix, venue in (
            ("long", str(position.get("long_exchange") or "")),
            ("short", str(position.get("short_exchange") or "")),
        ):
            snapshot = snapshots.get(f"{venue}|{symbol}")
            if not isinstance(snapshot, dict):
                continue
            try:
                rate = float(snapshot.get("fundingRate"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(rate):
                continue
            position[f"{prefix}_funding_rate"] = rate
            try:
                mark = float(snapshot.get("markPrice"))
            except (TypeError, ValueError):
                mark = math.nan
            if math.isfinite(mark) and mark > 0.0:
                position[f"{prefix}_funding_mark_price"] = mark
            if venue == "deribit":
                if math.isfinite(mark) and mark > 0.0:
                    position["funding_last_accrual_ms"] = opened_at_ms
            else:
                stamp = _snapshot_future_funding_timestamp(snapshot, now_ms=opened_at_ms)
                if stamp is not None:
                    position[f"{prefix}_funding_timestamp"] = stamp


def _process_pending_entries_v20(
    state: dict[str, Any],
    *,
    books_by_symbol: dict[str, dict[str, Any]],
    stats_db: str | Path,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    timeout_ms: int = 30_000,
    now_mono_ms: int | None = None,
    strict_maker_price_through: bool = False,
    terminal_outcome_recorder: Any = None,
) -> None:
    """Reuse V19 causal post-fill logic while recording terminal economics."""

    def record_terminal(
        pending: dict[str, Any],
        *,
        accepted: bool,
        realized_net_pnl: float | None,
    ) -> None:
        if terminal_outcome_recorder is not None:
            terminal_outcome_recorder(
                pending,
                accepted=accepted,
                realized_net_pnl=realized_net_pnl,
            )
            return
        side = str(pending.get("maker_side") or "").upper()
        if side not in {"LONG", "SHORT"}:
            raise ValueError("V20 pending entry is missing maker_side")
        venue = str(
            pending["long_exchange"] if side == "LONG" else pending["short_exchange"]
        )
        if accepted:
            record_v20_execution_outcome(
                stats_db, venue=venue, side=side, accepted=True
            )
            return
        if realized_net_pnl is None or not math.isfinite(float(realized_net_pnl)):
            raise ValueError("rejected V20 outcome requires realized net PnL")
        entry_price = float(
            pending["long_limit_price"] if side == "LONG" else pending["short_limit_price"]
        )
        maker_notional = float(pending["quantity"]) * entry_price
        if maker_notional <= 0.0:
            raise ValueError("V20 maker notional must be positive")
        reject_net_bps = float(realized_net_pnl) / maker_notional * 10_000.0
        # Calibration models the loss tail. A rare non-loss safety unwind is kept
        # in the journal/account PnL but must not be fabricated into a negative loss.
        record_v20_execution_outcome(
            stats_db,
            venue=venue,
            side=side,
            accepted=False,
            reject_net_bps=reject_net_bps,
        )
        if reject_net_bps >= 0.0:
            state["v20_nonloss_abort_count"] = int(
                state.get("v20_nonloss_abort_count", 0)
            ) + 1

    previous_position_ids = {
        str(position.get("position_id") or "")
        for position in state.get("open_positions", [])
    }
    _process_pending_entries_v19(
        state,
        books_by_symbol=books_by_symbol,
        stats_db=stats_db,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        timeout_ms=timeout_ms,
        now_mono_ms=now_mono_ms,
        strict_maker_price_through=strict_maker_price_through,
        execution_outcome_recorder=record_terminal,
    )
    _seed_new_position_funding_state(
        state, previous_position_ids=previous_position_ids
    )



def _process_maker_probes_v20(
    state: dict[str, Any],
    *,
    books_by_symbol: dict[str, dict[str, VenueBook]],
    stats_db: str | Path,
    now_ms: int,
    maker_fee_bps: dict[str, float],
    taker_fee_bps: dict[str, float],
    timeout_ms: int = 20_000,
    now_mono_ms: int | None = None,
    strict_maker_price_through: bool = False,
    shadow_outcome_recorder: Any = None,
    counter_prefix: str = "v20",
    feature_min_samples: int = 12,
    feature_minimum_window_samples: int = 3,
    feature_require_5m_window: bool = True,
    funding_max_hold_seconds: float = 65.0 * 60.0,
    price_discrete_funding: bool = False,
) -> None:
    """Learn single-maker terminal economics from causal shadow probes only."""

    def bump(suffix: str) -> None:
        key = f"{counter_prefix}_{suffix}"
        state[key] = int(state.get(key, 0)) + 1

    def record_shadow_side(
        probe: dict[str, Any],
        *,
        side: str,
        long_book: VenueBook,
        short_book: VenueBook,
        features: dict[str, float | int],
    ) -> None:
        quantity = float(probe.get("quantity", 0.0))
        if quantity <= 0.0:
            target = max(2.0, float(probe.get("target_notional", 0.0) or 0.0))
            quantity = min(
                target / float(probe["long_limit_price"]),
                target / float(probe["short_limit_price"]),
            )
        if quantity <= 0.0 or not math.isfinite(quantity):
            return

        long_venue = str(probe["long_exchange"])
        short_venue = str(probe["short_exchange"])
        funding = pair_funding_admission(
            long_venue=long_venue,
            short_venue=short_venue,
            long_snapshot=state.get("funding_snapshots", {}).get(f"{long_venue}|{probe['symbol']}"),
            short_snapshot=state.get("funding_snapshots", {}).get(f"{short_venue}|{probe['symbol']}"),
            now_ms=int(now_ms),
            max_hold_seconds=float(funding_max_hold_seconds),
            price_discrete_funding=price_discrete_funding,
        )
        if funding["blocked"]:
            bump("shadow_funding_block_count")
            return
        funding_cost_bps = float(funding["expected_funding_cost_bps"])
        baseline_60 = float(features["baseline_60m_bps"])
        baseline_15 = float(features["baseline_15m_bps"])
        sigma = max(0.5, float(features["route_sigma_bps"]))
        volatility = max(0.0, float(features["price_volatility_bps"]))
        exit_fees = float(taker_fee_bps[long_venue]) + float(taker_fee_bps[short_venue])
        adverse = max(0.25, 0.10 * sigma + 0.05 * volatility)
        adjusted_post_fill_ev: float | None = None

        if side == "LONG":
            maker_venue = long_venue
            maker_entry = float(probe["long_limit_price"])
            hedge = _market_fill(
                short_book,
                side="sell",
                quantity=quantity,
                fee_bps=float(taker_fee_bps[short_venue]),
            )
            if hedge is not None:
                post_fill = post_fill_entry_ev(
                    long_entry_price=maker_entry,
                    short_entry_price=float(hedge.vwap),
                    baseline_60m_bps=baseline_60,
                    baseline_15m_bps=baseline_15,
                    long_entry_fee_bps=float(maker_fee_bps[long_venue]),
                    short_entry_fee_bps=float(taker_fee_bps[short_venue]),
                    expected_exit_fee_bps=exit_fees,
                    expected_exit_price_improvement_bps=0.0,
                    adverse_selection_bps=adverse,
                    route_sigma_bps=sigma,
                    price_volatility_bps=volatility,
                    safety_buffer_bps=float(state.get("safety_buffer_bps", 0.5)),
                    placement_capture_bps=0.0,
                )
                adjusted_post_fill_ev = float(post_fill["post_fill_expected_value_bps"]) - funding_cost_bps
                if bool(post_fill["tradeable"]) and adjusted_post_fill_ev >= float(post_fill["minimum_required_ev_bps"]):
                    if shadow_outcome_recorder is not None:
                        shadow_outcome_recorder(
                            probe,
                            venue=maker_venue,
                            side=side,
                            accepted=True,
                            post_fill_ev_bps=adjusted_post_fill_ev,
                            reject_net_bps=None,
                        )
                    else:
                        record_v20_execution_outcome(
                            stats_db, venue=maker_venue, side=side, accepted=True
                        )
                    bump("shadow_accept_count")
                    return
            unwind = _market_fill(
                long_book,
                side="sell",
                quantity=quantity,
                fee_bps=float(taker_fee_bps[long_venue]),
            )
            if unwind is None:
                return
            exit_price = float(unwind.vwap)
            gross = quantity * (exit_price - maker_entry)
        elif side == "SHORT":
            maker_venue = short_venue
            maker_entry = float(probe["short_limit_price"])
            hedge = _market_fill(
                long_book,
                side="buy",
                quantity=quantity,
                fee_bps=float(taker_fee_bps[long_venue]),
            )
            if hedge is not None:
                post_fill = post_fill_entry_ev(
                    long_entry_price=float(hedge.vwap),
                    short_entry_price=maker_entry,
                    baseline_60m_bps=baseline_60,
                    baseline_15m_bps=baseline_15,
                    long_entry_fee_bps=float(taker_fee_bps[long_venue]),
                    short_entry_fee_bps=float(maker_fee_bps[short_venue]),
                    expected_exit_fee_bps=exit_fees,
                    expected_exit_price_improvement_bps=0.0,
                    adverse_selection_bps=adverse,
                    route_sigma_bps=sigma,
                    price_volatility_bps=volatility,
                    safety_buffer_bps=float(state.get("safety_buffer_bps", 0.5)),
                    placement_capture_bps=0.0,
                )
                adjusted_post_fill_ev = float(post_fill["post_fill_expected_value_bps"]) - funding_cost_bps
                if bool(post_fill["tradeable"]) and adjusted_post_fill_ev >= float(post_fill["minimum_required_ev_bps"]):
                    if shadow_outcome_recorder is not None:
                        shadow_outcome_recorder(
                            probe,
                            venue=maker_venue,
                            side=side,
                            accepted=True,
                            post_fill_ev_bps=adjusted_post_fill_ev,
                            reject_net_bps=None,
                        )
                    else:
                        record_v20_execution_outcome(
                            stats_db, venue=maker_venue, side=side, accepted=True
                        )
                    bump("shadow_accept_count")
                    return
            unwind = _market_fill(
                short_book,
                side="buy",
                quantity=quantity,
                fee_bps=float(taker_fee_bps[short_venue]),
            )
            if unwind is None:
                return
            exit_price = float(unwind.vwap)
            gross = quantity * (maker_entry - exit_price)
        else:
            raise ValueError("shadow maker side must be LONG or SHORT")

        entry_fee = quantity * maker_entry * float(maker_fee_bps[maker_venue]) / 10_000.0
        exit_fee = quantity * exit_price * float(taker_fee_bps[maker_venue]) / 10_000.0
        maker_notional = quantity * maker_entry
        reject_bps = (gross - entry_fee - exit_fee) / maker_notional * 10_000.0
        if shadow_outcome_recorder is not None:
            shadow_outcome_recorder(
                probe,
                venue=maker_venue,
                side=side,
                accepted=False,
                post_fill_ev_bps=adjusted_post_fill_ev,
                reject_net_bps=reject_bps,
            )
        else:
            record_v20_execution_outcome(
                stats_db,
                venue=maker_venue,
                side=side,
                accepted=False,
                reject_net_bps=reject_bps,
            )
        bump("shadow_reject_count")
        if reject_bps >= 0.0:
            bump("shadow_nonloss_reject_count")

    # Capture terminal causal outcomes before the reused V17 processor removes probes.
    for probe in list(state.get("maker_probes", [])):
        if int(now_ms) <= int(probe["placed_at_ms"]):
            continue
        venues = books_by_symbol.get(str(probe["symbol"]), {})
        long_book = venues.get(str(probe["long_exchange"]))
        short_book = venues.get(str(probe["short_exchange"]))
        if long_book is None or short_book is None:
            continue
        long_fill = passive_limit_filled(
            "buy",
            float(probe["long_limit_price"]),
            long_book.book,
            placed_at_ms=int(probe["placed_at_ms"]),
            placed_at_mono_ms=probe.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
            queue_ahead_quantity=probe.get("long_queue_ahead_quantity"),
            order_quantity=probe.get("quantity"),
            trade_volume_baseline=probe.get("long_trade_volume_baseline"),
        )
        short_fill = passive_limit_filled(
            "sell",
            float(probe["short_limit_price"]),
            short_book.book,
            placed_at_ms=int(probe["placed_at_ms"]),
            placed_at_mono_ms=probe.get("placed_at_mono_ms"),
            strict_price_through=strict_maker_price_through,
            queue_ahead_quantity=probe.get("short_queue_ahead_quantity"),
            order_quantity=probe.get("quantity"),
            trade_volume_baseline=probe.get("short_trade_volume_baseline"),
        )
        if not long_fill and not short_fill:
            continue
        features = multi_horizon_route_features(
            stats_db,
            str(probe["symbol"]),
            str(probe["long_exchange"]),
            str(probe["short_exchange"]),
            now_ms=now_ms,
            min_samples=feature_min_samples,
            minimum_span_ms=420_000,
            minimum_window_samples=feature_minimum_window_samples,
            require_5m_window=feature_require_5m_window,
        )
        if features is None:
            continue
        if long_fill:
            record_shadow_side(
                probe,
                side="LONG",
                long_book=long_book,
                short_book=short_book,
                features=features,
            )
        if short_fill:
            record_shadow_side(
                probe,
                side="SHORT",
                long_book=long_book,
                short_book=short_book,
                features=features,
            )

    _process_maker_probes(
        state,
        books_by_symbol=books_by_symbol,
        stats_db=stats_db,
        now_ms=now_ms,
        timeout_ms=timeout_ms,
        now_mono_ms=now_mono_ms,
        strict_maker_price_through=strict_maker_price_through,
    )


V20_TAKER_FEE_BPS: dict[str, float] = {}
V20_MAKER_FEE_BPS: dict[str, float] = {}


def _ensure_v20_runtime_imports() -> tuple[dict[str, float], dict[str, float]]:
    global V20_TAKER_FEE_BPS, V20_MAKER_FEE_BPS
    if V20_TAKER_FEE_BPS:
        return V20_TAKER_FEE_BPS, V20_MAKER_FEE_BPS
    if __package__:
        from .run_arbitrage_paper_v12 import DEFAULT_FEE_BPS
    else:
        from run_arbitrage_paper_v12 import DEFAULT_FEE_BPS
    from crypto_research.maker_v17 import DEFAULT_MAKER_FEE_BPS

    V20_TAKER_FEE_BPS = {**DEFAULT_FEE_BPS, "deribit": 3.5}
    V20_MAKER_FEE_BPS = {**DEFAULT_MAKER_FEE_BPS, "deribit": 1.5}
    return V20_TAKER_FEE_BPS, V20_MAKER_FEE_BPS


def _eligible_linear_stable_swap(market: dict[str, Any]) -> bool:
    quote = str(market.get("quote") or "").upper()
    settle = str(market.get("settle") or "").upper()
    return bool(
        market.get("swap") is True
        and market.get("linear") is True
        and quote == settle
        and quote in {"USDT", "USDC"}
        and market.get("active") is not False
    )


def make_public_stream_clients_v20() -> dict[str, Any]:
    """Credential-free public clients with latency-safe funding semantics."""

    from crypto_research.stream_v18 import make_public_stream_clients

    # Deribit remains implemented/tested but is intentionally not in the production
    # universe until a causal mark-price stream can be maintained without REST-loop drag.
    return make_public_stream_clients()


def make_public_funding_clients_v20() -> dict[str, Any]:
    """Create credential-free REST-only clients for isolated funding refreshes."""

    import ccxt.async_support as ccxt_async

    common = {"enableRateLimit": True}
    return {
        "binance": ccxt_async.binanceusdm(common.copy()),
        "okx": ccxt_async.okx({**common, "options": {"defaultType": "swap"}}),
        "mexc": ccxt_async.mexc({**common, "options": {"defaultType": "swap"}}),
        "bybit": ccxt_async.bybit({**common, "options": {"defaultType": "swap"}}),
        "bitget": ccxt_async.bitget({**common, "options": {"defaultType": "swap"}}),
        "kucoin": ccxt_async.kucoinfutures(common.copy()),
        "gate": ccxt_async.gate({**common, "options": {"defaultType": "swap"}}),
    }


async def _load_coverage_v20(clients: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    import asyncio

    results = await asyncio.gather(
        *(client.load_markets() for client in clients.values()),
        return_exceptions=True,
    )
    coverage: dict[str, set[str]] = {}
    for (venue, _), markets in zip(clients.items(), results, strict=True):
        if isinstance(markets, BaseException) or not isinstance(markets, dict):
            continue
        for market in markets.values():
            if _eligible_linear_stable_swap(market):
                coverage.setdefault(str(market["symbol"]), set()).add(venue)
    return {
        symbol: tuple(sorted(venues))
        for symbol, venues in coverage.items()
        if len(venues) >= 2
    }


async def _refresh_funding_snapshots_v20(
    *,
    clients: dict[str, Any],
    state: dict[str, Any],
    symbols: list[str],
    coverage: dict[str, tuple[str, ...]],
    now_ms: int,
    refresh_interval_ms: int = 60_000,
    request_timeout_seconds: float = 15.0,
) -> None:
    """Refresh batch funding globally and slow single-symbol venues on demand."""

    import asyncio

    snapshots = state.setdefault("funding_snapshots", {})
    requested_symbols = {str(symbol) for symbol in symbols if symbol in coverage}
    active_pairs = {
        (str(position.get(key) or ""), str(position.get("symbol") or ""))
        for position in state.get("open_positions", [])
        if isinstance(position, dict)
        for key in ("long_exchange", "short_exchange")
        if position.get(key) and position.get("symbol")
    }
    requested_symbols.update(symbol for _, symbol in active_pairs if symbol in coverage)
    last_full_refresh_ms = int(state.get("funding_last_full_refresh_ms", 0) or 0)
    full_refresh_due = last_full_refresh_ms <= 0 or int(now_ms) - last_full_refresh_ms >= int(refresh_interval_ms)

    by_venue: dict[str, list[str]] = {}
    for venue, client in clients.items():
        can_batch = bool(getattr(client, "has", {}).get("fetchFundingRates")) and hasattr(client, "fetch_funding_rates")
        if can_batch and full_refresh_due:
            by_venue[venue] = sorted(
                symbol for symbol, venues in coverage.items() if venue in venues
            )
            continue
        for symbol in sorted(requested_symbols):
            if venue not in coverage.get(symbol, ()):
                continue
            snapshot = snapshots.get(f"{venue}|{symbol}")
            sampled_at_ms = int(snapshot.get("sampled_at_ms", 0) or 0) if isinstance(snapshot, dict) else 0
            if sampled_at_ms <= 0 or int(now_ms) - sampled_at_ms >= int(refresh_interval_ms):
                by_venue.setdefault(venue, []).append(symbol)

    single_sem = asyncio.Semaphore(8)

    async def public_call(coro: Any) -> Any:
        return await asyncio.wait_for(coro, timeout=float(request_timeout_seconds))

    async def fetch_venue(venue: str, venue_symbols: list[str]) -> tuple[str, list[str], Any]:
        client = clients[venue]
        can_batch = bool(getattr(client, "has", {}).get("fetchFundingRates")) and hasattr(client, "fetch_funding_rates")
        if can_batch:
            try:
                return venue, venue_symbols, await public_call(client.fetch_funding_rates(venue_symbols))
            except Exception as exc:
                return venue, venue_symbols, exc

        async def fetch_one(symbol: str) -> tuple[str, Any]:
            async with single_sem:
                try:
                    return symbol, await public_call(client.fetch_funding_rate(symbol))
                except Exception as exc:
                    return symbol, exc

        rows = dict(await asyncio.gather(*(fetch_one(symbol) for symbol in venue_symbols)))
        return venue, venue_symbols, rows

    state.setdefault("funding_snapshot_error_count", 0)
    results = await asyncio.gather(
        *(fetch_venue(venue, venue_symbols) for venue, venue_symbols in by_venue.items())
    )
    errors = 0
    venue_rows: dict[str, tuple[list[str], dict[str, Any]]] = {}
    for venue, venue_symbols, result in results:
        if isinstance(result, Exception):
            venue_rows[venue] = (venue_symbols, {symbol: result for symbol in venue_symbols})
            continue
        if isinstance(result, list):
            result = {str(row.get("symbol") or ""): row for row in result if isinstance(row, dict)}
        if not isinstance(result, dict):
            exc = RuntimeError("invalid funding batch response")
            venue_rows[venue] = (venue_symbols, {symbol: exc for symbol in venue_symbols})
            continue
        venue_rows[venue] = (venue_symbols, dict(result))

    async def fetch_single_fallback(venue: str, symbol: str) -> tuple[str, str, Any]:
        client = clients[venue]
        if not hasattr(client, "fetch_funding_rate"):
            return venue, symbol, RuntimeError("single funding endpoint unavailable")
        async with single_sem:
            try:
                return venue, symbol, await public_call(client.fetch_funding_rate(symbol))
            except Exception as exc:
                return venue, symbol, exc

    fallback_requests: list[tuple[str, str]] = []
    deferred_fallbacks: set[tuple[str, str]] = set()
    for venue, (venue_symbols, rows) in venue_rows.items():
        for symbol in venue_symbols:
            row = rows.get(symbol)
            missing_discrete_timestamp = (
                isinstance(row, dict)
                and venue != "deribit"
                and row.get("fundingTimestamp") is None
                and row.get("nextFundingTimestamp") is None
            )
            if isinstance(row, Exception) or not isinstance(row, dict) or missing_discrete_timestamp:
                # Full-universe batch endpoints can omit fields that only exist on
                # per-symbol endpoints. Do not turn one batch miss into O(universe)
                # REST calls; discovery/active symbols are repaired on demand.
                if symbol not in requested_symbols:
                    deferred_fallbacks.add((venue, symbol))
                    continue
                fallback_requests.append((venue, symbol))

    if fallback_requests:
        fallback_rows = await asyncio.gather(
            *(fetch_single_fallback(venue, symbol) for venue, symbol in fallback_requests)
        )
        for venue, symbol, row in fallback_rows:
            if venue in venue_rows:
                venue_rows[venue][1][symbol] = row

    for venue, (venue_symbols, rows) in venue_rows.items():
        for symbol in venue_symbols:
            if (venue, symbol) in deferred_fallbacks:
                continue
            row = rows.get(symbol)
            if isinstance(row, Exception) or not isinstance(row, dict):
                errors += 1
                continue
            try:
                rate = float(row.get("fundingRate"))
            except (TypeError, ValueError):
                errors += 1
                continue
            if not math.isfinite(rate):
                errors += 1
                continue
            if venue != "deribit" and row.get("fundingTimestamp") is None and row.get("nextFundingTimestamp") is None:
                errors += 1
                continue
            raw_mark = row.get("markPrice")
            if raw_mark is None and venue == "mexc":
                raw_mark = (row.get("info") or {}).get("fairPrice")
            try:
                mark_price = float(raw_mark)
            except (TypeError, ValueError):
                mark_price = math.nan
            snapshots[f"{venue}|{symbol}"] = {
                "venue": venue,
                "symbol": symbol,
                "fundingRate": rate,
                "fundingTimestamp": row.get("fundingTimestamp"),
                "nextFundingTimestamp": row.get("nextFundingTimestamp"),
                "interval": row.get("interval"),
                "markPrice": mark_price if math.isfinite(mark_price) and mark_price > 0.0 else None,
                "indexPrice": row.get("indexPrice"),
                "sampled_at_ms": int(now_ms),
            }

    if full_refresh_due:
        state["funding_last_full_refresh_ms"] = int(now_ms)
        state["funding_full_refresh_count"] = int(state.get("funding_full_refresh_count", 0)) + 1

    async def fetch_active_mark(venue: str, symbol: str) -> tuple[str, str, float | None]:
        snapshot = snapshots.get(f"{venue}|{symbol}")
        if not isinstance(snapshot, dict) or snapshot.get("markPrice") is not None:
            return venue, symbol, None
        client = clients.get(venue)
        if client is None:
            return venue, symbol, None
        if bool(getattr(client, "has", {}).get("fetchMarkPrice")) and hasattr(client, "fetch_mark_price"):
            try:
                ticker = await public_call(client.fetch_mark_price(symbol))
                value = float(ticker.get("last"))
                if math.isfinite(value) and value > 0.0:
                    return venue, symbol, value
            except Exception:
                return venue, symbol, None
        return venue, symbol, None

    if active_pairs:
        mark_rows = await asyncio.gather(
            *(fetch_active_mark(venue, symbol) for venue, symbol in sorted(active_pairs))
        )
        for venue, symbol, mark_price in mark_rows:
            if mark_price is not None and isinstance(snapshots.get(f"{venue}|{symbol}"), dict):
                snapshots[f"{venue}|{symbol}"]["markPrice"] = float(mark_price)

    state["funding_snapshot_error_count"] = int(state.get("funding_snapshot_error_count", 0)) + errors
    state["funding_snapshot_count"] = len(snapshots)

def _accrue_v20_continuous_funding(
    state: dict[str, Any],
    *,
    clients: dict[str, Any],
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    accrual_interval_ms: int = 60_000,
) -> None:
    """Accrue continuous Deribit carry and fail-safe discrete settlements."""

    del clients
    snapshots = state.get("funding_snapshots", {})

    def apply_cashflow(
        *,
        position: dict[str, Any],
        venue: str,
        side: str,
        symbol: str,
        rate: float,
        notional: float,
        cashflow: float,
        elapsed_seconds: float | None = None,
        funding_timestamp_ms: int | None = None,
    ) -> None:
        state["venue_balances"][venue] = float(state["venue_balances"].get(venue, 0.0)) + cashflow
        state["equity"] = float(sum(float(value) for value in state["venue_balances"].values()))
        state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + cashflow
        state["realized_funding_pnl"] = float(state.get("realized_funding_pnl", 0.0)) + cashflow
        position["funding_pnl"] = float(position.get("funding_pnl", 0.0)) + cashflow
        event = {
            "record_type": "PAPER_FUNDING_ACCRUAL",
            "position_id": str(position.get("position_id") or ""),
            "symbol": symbol,
            "venue": venue,
            "side": side,
            "funding_rate": float(rate),
            "funding_notional": float(notional),
            "gross_pnl": 0.0,
            "fees": 0.0,
            "funding_pnl": float(cashflow),
            "realized_net_pnl": float(cashflow),
            "realized_at": now_utc,
        }
        if elapsed_seconds is not None:
            event["elapsed_seconds"] = float(elapsed_seconds)
        if funding_timestamp_ms is not None:
            event["funding_timestamp_ms"] = int(funding_timestamp_ms)
        _append_jsonl(journal_path, event)

    for position in state.get("open_positions", []):
        symbol = str(position.get("symbol") or "")
        quantity = float(position.get("quantity", 0.0) or 0.0)
        if not symbol or quantity <= 0.0:
            continue
        for side, prefix, venue in (
            ("LONG", "long", str(position.get("long_exchange") or "")),
            ("SHORT", "short", str(position.get("short_exchange") or "")),
        ):
            snapshot = snapshots.get(f"{venue}|{symbol}")
            if not isinstance(snapshot, dict):
                state["funding_accrual_data_miss_count"] = int(state.get("funding_accrual_data_miss_count", 0)) + 1
                continue
            try:
                current_rate = float(snapshot.get("fundingRate"))
                current_mark = float(snapshot.get("markPrice"))
            except (TypeError, ValueError):
                current_rate = math.nan
                current_mark = math.nan
            if not math.isfinite(current_rate) or not math.isfinite(current_mark) or current_mark <= 0.0:
                state["funding_accrual_data_miss_count"] = int(state.get("funding_accrual_data_miss_count", 0)) + 1
                continue

            rate_key = f"{prefix}_funding_rate"
            mark_key = f"{prefix}_funding_mark_price"
            last_rate = position.get(rate_key)
            last_mark = position.get(mark_key)

            if venue == "deribit":
                anchor = int(position.get("funding_last_accrual_ms", position.get("opened_at_ms", now_ms)))
                if last_rate is None or last_mark is None:
                    # New V20 positions are normally seeded at open. This fallback is
                    # for restored legacy state and starts only from the observation time.
                    position[rate_key] = current_rate
                    position[mark_key] = current_mark
                    position["funding_last_accrual_ms"] = int(now_ms)
                    continue
                elapsed_ms = max(0, int(now_ms) - anchor)
                if elapsed_ms < int(accrual_interval_ms):
                    continue
                last_rate = float(last_rate)
                last_mark = float(last_mark)
                if not math.isfinite(last_rate) or not math.isfinite(last_mark) or last_mark <= 0.0:
                    state["funding_accrual_data_miss_count"] = int(state.get("funding_accrual_data_miss_count", 0)) + 1
                    continue
                notional = quantity * last_mark
                elapsed_seconds = elapsed_ms / 1000.0
                cashflow = accrue_deribit_funding_cashflow(
                    side=side,
                    notional=notional,
                    funding_rate=last_rate,
                    elapsed_seconds=elapsed_seconds,
                )
                apply_cashflow(
                    position=position, venue=venue, side=side, symbol=symbol,
                    rate=last_rate, notional=notional, cashflow=cashflow,
                    elapsed_seconds=elapsed_seconds,
                )
                position["funding_last_accrual_ms"] = int(now_ms)
                position[rate_key] = current_rate
                position[mark_key] = current_mark
                continue

            timestamp_key = f"{prefix}_funding_timestamp"
            settled_key = f"{prefix}_funding_settled_timestamp"
            scheduled = position.get(timestamp_key)
            current_future = _snapshot_future_funding_timestamp(snapshot, now_ms=int(now_ms))
            if scheduled is None:
                if current_future is not None:
                    position[timestamp_key] = int(current_future)
                    position[rate_key] = current_rate
                    position[mark_key] = current_mark
                continue
            try:
                scheduled_ms = int(scheduled)
                settled_ms = int(position.get(settled_key, 0) or 0)
            except (TypeError, ValueError):
                state["funding_accrual_data_miss_count"] = int(state.get("funding_accrual_data_miss_count", 0)) + 1
                continue

            # Before settlement, keep the latest causal quote for the same event.
            if int(now_ms) < scheduled_ms:
                if current_future == scheduled_ms:
                    position[rate_key] = current_rate
                    position[mark_key] = current_mark
                continue

            if settled_ms < scheduled_ms:
                try:
                    event_rate = float(last_rate)
                    event_mark = float(last_mark)
                except (TypeError, ValueError):
                    event_rate = math.nan
                    event_mark = math.nan
                if not math.isfinite(event_rate) or not math.isfinite(event_mark) or event_mark <= 0.0:
                    state["funding_accrual_data_miss_count"] = int(state.get("funding_accrual_data_miss_count", 0)) + 1
                    continue
                notional = quantity * event_mark
                cashflow = accrue_discrete_funding_cashflow(
                    side=side, notional=notional, funding_rate=event_rate
                )
                apply_cashflow(
                    position=position, venue=venue, side=side, symbol=symbol,
                    rate=event_rate, notional=notional, cashflow=cashflow,
                    funding_timestamp_ms=scheduled_ms,
                )
                position[settled_key] = scheduled_ms

            # Once the public endpoint advances, arm the next event.
            if current_future is not None and current_future > scheduled_ms:
                position[timestamp_key] = int(current_future)
                position[rate_key] = current_rate
                position[mark_key] = current_mark


def _refresh_v20_state(state: dict[str, Any]) -> None:
    state["schema_version"] = SCHEMA_VERSION
    state["portfolio_model"] = PORTFOLIO_MODEL
    state["strategy_id"] = STRATEGY_ID
    state["exchange_leverage"] = 40.0
    state["min_position_leverage"] = 20.0
    state["max_position_leverage"] = 40.0
    state["execution_model"] = "SINGLE_MAKER_CAUSAL_TAKER_HEDGE"
    state["math_model_revision"] = "CONTRACT_BASE_FUNDING_AWARE_V2"
    state["disabled_public_venues"] = {
        "deribit": "CAUSAL_MARK_FEED_NOT_LATENCY_SAFE_FOR_PRODUCTION"
    }
    state["maker_fill_calibration_source"] = "V20_FRESH_CAUSAL_SHADOW_ONLY"
    state["account_objective"] = "REALIZED_NET_PNL_PER_HOUR"
    state["target_realized_pnl_per_hour"] = TARGET_ACCOUNT_PNL_PER_HOUR
    state.setdefault("v20_shadow_accept_count", 0)
    state.setdefault("v20_shadow_reject_count", 0)
    state.setdefault("v20_shadow_nonloss_reject_count", 0)
    state.setdefault("v20_nonloss_abort_count", 0)
    state.setdefault("seeded_v19_execution_outcome_count", 0)
    state.setdefault("funding_snapshots", {})
    state.setdefault("funding_snapshot_error_count", 0)
    state.setdefault("funding_snapshot_count", 0)
    state.setdefault("realized_funding_pnl", 0.0)
    state.setdefault("funding_accrual_data_miss_count", 0)


def _default_state_v20(
    venue_names: list[str],
    *,
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    if __package__:
        from .run_arbitrage_paper_v19 import _default_state_v19
    else:
        from run_arbitrage_paper_v19 import _default_state_v19

    state = _default_state_v19(
        venue_names,
        initial_equity=initial_equity,
        gross_leverage_cap=gross_leverage_cap,
        max_open_positions=max_open_positions,
    )
    _refresh_v20_state(state)
    return state


def _assert_v20_invariants(state: dict[str, Any]) -> None:
    if __package__:
        from .run_arbitrage_paper_v19 import _assert_v19_invariants
    else:
        from run_arbitrage_paper_v19 import _assert_v19_invariants

    _assert_v19_invariants(
        state,
        expected_strategy_id=STRATEGY_ID,
        refresh_state=False,
    )
    for pending in state.get("pending_entries", []):
        side = str(pending.get("maker_side") or "").upper()
        if side and side not in {"LONG", "SHORT"}:
            raise ValueError("V20 pending entry maker side is invalid")
    _refresh_v20_state(state)


def load_state_v20(
    path: str | Path,
    *,
    venue_names: list[str],
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    import json

    if __package__:
        from .run_arbitrage_paper_v17 import _refresh_v17_margin
    else:
        from run_arbitrage_paper_v17 import _refresh_v17_margin

    state_path = Path(path)
    if not state_path.exists():
        return _default_state_v20(
            venue_names,
            initial_equity=initial_equity,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
        )
    with state_path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V20 paper state schema")
    defaults = _default_state_v20(
        venue_names,
        initial_equity=initial_equity,
        gross_leverage_cap=gross_leverage_cap,
        max_open_positions=max_open_positions,
    )
    for key, value in defaults.items():
        if key != "venue_balances":
            state.setdefault(key, value)
    balances = state.setdefault("venue_balances", {})
    for venue in venue_names:
        balances.setdefault(venue, 0.0)
    _refresh_v17_margin(state)
    _refresh_v20_state(state)
    _assert_v20_invariants(state)
    return state


def run_cycle_v20(
    *,
    clients: dict[str, Any],
    symbols: list[str],
    state: dict[str, Any],
    history_db: str | Path,
    now_ms: int,
    now_utc: str,
    journal_path: Path,
    symbol_venues: dict[str, tuple[str, ...]],
    max_book_age_ms: int = 5_000,
    depth_limit: int = 20,
    safety_buffer_bps: float = 0.5,
    monotonic_ms: int | None = None,
    max_pending_entries: int = 2,
    max_probes: int = 8,
) -> None:
    if __package__:
        from .run_arbitrage_paper_v17 import run_cycle_v17
        from .run_arbitrage_paper_v19 import _confirm_v19_exit
    else:
        from run_arbitrage_paper_v17 import run_cycle_v17
        from run_arbitrage_paper_v19 import _confirm_v19_exit
    from crypto_research.maker_v20 import select_v20_profile

    taker_fees, maker_fees = _ensure_v20_runtime_imports()
    state["safety_buffer_bps"] = float(safety_buffer_bps)
    _accrue_v20_continuous_funding(
        state,
        clients=clients,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
    )

    def decide_route(opportunity: ArbitrageOpportunity, **kwargs: Any) -> dict[str, Any]:
        return _v20_route_decision(
            opportunity,
            funding_snapshots=state.get("funding_snapshots", {}),
            now_ms=now_ms,
            attempt_capacity_per_hour=max(1.0, float(max_pending_entries)) * 3600.0 / PENDING_ENTRY_TIMEOUT_SECONDS,
            **kwargs,
        )

    def process_probes(current_state: dict[str, Any], **kwargs: Any) -> None:
        _process_maker_probes_v20(
            current_state,
            maker_fee_bps=maker_fees,
            taker_fee_bps=taker_fees,
            **kwargs,
        )

    run_cycle_v17(
        clients=clients,
        symbols=symbols,
        state=state,
        history_db=history_db,
        stats_db=history_db,
        safety_buffer_bps=safety_buffer_bps,
        depth_limit=depth_limit,
        taker_fee_bps=taker_fees,
        maker_fee_bps=maker_fees,
        max_book_age_ms=max_book_age_ms,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
        symbol_venues=symbol_venues,
        profile_selector=select_v20_profile,
        pending_entry_processor=_process_pending_entries_v20,
        route_decider=decide_route,
        reprofile_after_reprice=True,
        maker_probe_processor=process_probes,
        invariant_checker=_assert_v20_invariants,
        max_pending_entries=max_pending_entries,
        max_probes=max_probes,
        strategy_id=STRATEGY_ID,
        exit_decision_filter=_confirm_v19_exit,
        monotonic_ms=monotonic_ms,
        per_symbol_history_sampling=True,
        minimum_history_span_ms=420_000,
        strict_maker_price_through=True,
    )
    _refresh_v20_state(state)


def _initialize_v20_runtime(
    *,
    state: dict[str, Any],
    history_db: Path,
    artifacts: Path,
    args: Any,
    symbols: list[str],
    coverage: dict[str, tuple[str, ...]],
) -> None:
    from crypto_research.maker_v20 import seed_v20_execution_outcomes

    if args.seed_execution_journal is not None:
        journal = Path(args.seed_execution_journal)
        if journal.exists():
            seeded = seed_v20_execution_outcomes(history_db, journal)
            state["seeded_v19_execution_outcome_count"] = int(
                state.get("seeded_v19_execution_outcome_count", 0)
            ) + int(seeded)
    state["v20_stable_settles"] = ["USDT", "USDC"]
    state["v20_new_public_venues"] = []
    state["v20_symbol_limit"] = len(symbols)
    _refresh_v20_state(state)


def _mark_open_positions_v20(
    state: dict[str, Any], clients: dict[str, Any], *, marked_at_utc: str
) -> None:
    if __package__:
        from .run_arbitrage_paper_v19 import _mark_open_positions_v19
    else:
        from run_arbitrage_paper_v19 import _mark_open_positions_v19

    taker_fees, _ = _ensure_v20_runtime_imports()
    _mark_open_positions_v19(
        state,
        clients,
        marked_at_utc=marked_at_utc,
        taker_fee_bps=taker_fees,
    )
    _refresh_v20_state(state)


def _parser_v20():
    if __package__:
        from .run_arbitrage_paper_v19 import _parser as parser_v19
    else:
        from run_arbitrage_paper_v19 import _parser as parser_v19

    parser = parser_v19()
    parser.description = __doc__
    # ponytail: 50 symbols is the verified ceiling for this ~2 GiB host;
    # explicit --symbols can scale higher after CPU/event-loop capacity testing.
    parser.set_defaults(
        symbols=50,
        scan_batch_size=8,
        max_probes=8,
        artifacts_dir=Path("artifacts/arbitrage_v20_live"),
        seed_history_db=None,
    )
    parser.add_argument(
        "--seed-execution-journal",
        type=Path,
        default=None,
    )
    return parser


def _validate_v20_args(args: Any) -> None:
    if args.interval <= 0.0 or args.stream_warmup_seconds <= 0.0:
        raise ValueError("interval and stream warmup must be positive")
    if args.scan_batch_size <= 0 or args.max_pending_entries <= 0 or args.max_probes <= 0:
        raise ValueError("scan batch, pending entry, and probe limits must be positive")
    if args.max_book_age_ms <= 0:
        raise ValueError("book age limit must be positive")
    if args.max_book_skew_ms is not None:
        raise ValueError("V20 receive-skew filter is disabled; omit --max-book-skew-ms")
    if not 20.0 <= args.gross_leverage_cap <= 40.0:
        raise ValueError("V20 gross leverage cap must be in 20x..40x")
    memory_limits = (float(args.memory_high_water_mb), float(args.memory_hard_limit_mb))
    if not all(math.isfinite(value) and value > 0.0 for value in memory_limits):
        raise ValueError("memory limits must be finite and positive")
    if args.memory_hard_limit_mb <= args.memory_high_water_mb:
        raise ValueError("memory hard limit must exceed the soft high-water mark")
    if args.memory_hard_limit_mb > 3_000.0:
        raise ValueError("memory hard limit must not exceed 3000 MB")
    if args.symbols <= 0:
        raise ValueError("symbol limit must be positive")
    if __package__:
        from .run_arbitrage_paper_v19 import _host_memory_limit_mb
    else:
        from run_arbitrage_paper_v19 import _host_memory_limit_mb
    host_memory_mb = _host_memory_limit_mb()
    if host_memory_mb is not None and args.memory_hard_limit_mb > host_memory_mb * 0.80:
        raise ValueError("memory hard limit exceeds the host memory budget with required headroom")


async def _run_v20(args: Any) -> int:
    if __package__:
        from .run_arbitrage_paper_v19 import _run as run_shared
    else:
        from run_arbitrage_paper_v19 import _run as run_shared

    return await run_shared(
        args,
        cycle_runner=run_cycle_v20,
        state_loader=load_state_v20,
        coverage_loader=_load_coverage_v20,
        clients_factory=make_public_stream_clients_v20,
        history_filename="history_v20.sqlite",
        health_schema_version=HEALTH_SCHEMA_VERSION,
        state_initializer=_initialize_v20_runtime,
        mark_positions=_mark_open_positions_v20,
        runtime_label="V20",
        runtime_refresher=_refresh_funding_snapshots_v20,
    )


def main(argv: list[str] | None = None) -> int:
    import asyncio

    args = _parser_v20().parse_args(argv)
    _validate_v20_args(args)
    return asyncio.run(_run_v20(args))


if __name__ == "__main__":
    raise SystemExit(main())
