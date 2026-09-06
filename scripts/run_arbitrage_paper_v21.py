"""V21 cohort-calibrated, risk-adjusted paper arbitrage runner."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from crypto_research.arbitrage_v12 import ArbitrageOpportunity, VenueBook
from crypto_research.maker_v21 import (
    capture_bucket_v21,
    ensure_v21_execution_schema,
    record_v21_execution_outcome,
    v21_execution_calibration,
    v21_exit_decision,
    v21_single_maker_attempt_ev,
)

if __package__:
    from . import run_arbitrage_paper_v20 as v20
else:
    import run_arbitrage_paper_v20 as v20


SCHEMA_VERSION = "v21-arbitrage-paper-1"
HEALTH_SCHEMA_VERSION = "v21-arbitrage-health-1"
PORTFOLIO_MODEL = "WS_COHORT_CALIBRATED_SINGLE_MAKER_V2"
STRATEGY_ID = PORTFOLIO_MODEL
MATH_MODEL_REVISION = "COHORT_EXECUTION_FUNDING_AWARE_V3"


def _v21_calibration_provider(
    db_path: str | Path,
    *,
    venue: str,
    side: str,
    placement_capture_bps: float,
) -> dict[str, Any]:
    return v21_execution_calibration(
        db_path,
        venue=venue,
        side=side,
        placement_capture_bps=placement_capture_bps,
    )


def _cycle_v21_calibration_provider(
    cache: dict[tuple[str, str, str, str], dict[str, Any]],
    db_path: str | Path,
    *,
    venue: str,
    side: str,
    placement_capture_bps: float,
) -> dict[str, Any]:
    key = (
        str(db_path),
        str(venue).strip().lower(),
        str(side).upper(),
        capture_bucket_v21(placement_capture_bps),
    )
    if key not in cache:
        cache[key] = _v21_calibration_provider(
            db_path,
            venue=venue,
            side=side,
            placement_capture_bps=placement_capture_bps,
        )
    return cache[key]


def _v21_route_decision(
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
    calibration_provider: Any = _v21_calibration_provider,
) -> dict[str, Any]:
    decision = v20._v20_route_decision(
        opportunity,
        features=features,
        stats_db=stats_db,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        safety_buffer_bps=safety_buffer_bps,
        venues=venues,
        funding_snapshots=funding_snapshots,
        now_ms=now_ms,
        attempt_capacity_per_hour=attempt_capacity_per_hour,
        max_hold_seconds=35.0 * 60.0,
        price_discrete_funding=True,
        calibration_provider=calibration_provider,
        attempt_ev_function=v21_single_maker_attempt_ev,
    )
    pair_value = float(decision.get("max_conditional_pair_value_bps", 0.0))
    capture = float(decision.get("capture_bps", 0.0))
    shadow_eligible = bool(decision.get("funding_ready", False)) and capture > 0.0 and pair_value > 0.0
    decision["shadow_probe_eligible"] = shadow_eligible
    decision["shadow_probe_priority"] = pair_value if shadow_eligible else 0.0
    return decision


def _confirm_v21_exit(
    state: dict[str, Any],
    position: dict[str, Any],
    reason: str | None,
    *,
    now_ms: int,
) -> str | None:
    key = str(position.get("position_id") or position.get("position_key") or "")
    confirmations = state.setdefault("v21_exit_confirmations", {})
    if reason != "DIVERGENCE_STOP":
        confirmations.pop(key, None)
        return reason
    previous = confirmations.get(key)
    if not isinstance(previous, dict):
        confirmations[key] = {"count": 1, "first_ms": int(now_ms)}
        return None
    count = int(previous.get("count", 0)) + 1
    first_ms = int(previous.get("first_ms", now_ms))
    previous.update({"count": count, "last_ms": int(now_ms)})
    if count >= 2 and int(now_ms) - first_ms >= 500:
        confirmations.pop(key, None)
        return reason
    return None


def _record_v21_shadow_outcome(
    stats_db: str | Path,
    now_ms: int,
    probe: dict[str, Any],
    *,
    venue: str,
    side: str,
    accepted: bool,
    post_fill_ev_bps: float | None,
    reject_net_bps: float | None,
) -> None:
    record_v21_execution_outcome(
        stats_db,
        venue=venue,
        side=side,
        placement_capture_bps=float(probe.get("placement_capture_bps", 0.0)),
        post_fill_ev_bps=post_fill_ev_bps,
        accepted=accepted,
        reject_net_bps=reject_net_bps,
        observed_at_ms=now_ms,
    )


def _record_v21_pending_outcome(
    stats_db: str | Path,
    now_ms: int,
    state: dict[str, Any],
    pending: dict[str, Any],
    *,
    accepted: bool,
    realized_net_pnl: float | None,
) -> None:
    side = str(pending.get("maker_side") or "").upper()
    if side not in {"LONG", "SHORT"}:
        raise ValueError("V21 pending entry is missing maker_side")
    venue = str(
        pending["long_exchange"] if side == "LONG" else pending["short_exchange"]
    )
    reject_net_bps: float | None = None
    if not accepted:
        if realized_net_pnl is None or not math.isfinite(float(realized_net_pnl)):
            raise ValueError("rejected V21 outcome requires realized net PnL")
        entry_price = float(
            pending["long_limit_price"] if side == "LONG" else pending["short_limit_price"]
        )
        maker_notional = float(pending["quantity"]) * entry_price
        if maker_notional <= 0.0:
            raise ValueError("V21 maker notional must be positive")
        reject_net_bps = float(realized_net_pnl) / maker_notional * 10_000.0
        if reject_net_bps >= 0.0:
            state["v21_nonloss_abort_count"] = int(
                state.get("v21_nonloss_abort_count", 0)
            ) + 1
    raw_post_fill = pending.get("post_fill_expected_value_bps")
    post_fill_ev = None if raw_post_fill is None else float(raw_post_fill)
    record_v21_execution_outcome(
        stats_db,
        venue=venue,
        side=side,
        placement_capture_bps=float(pending.get("capture_bps", 0.0)),
        post_fill_ev_bps=post_fill_ev,
        accepted=accepted,
        reject_net_bps=reject_net_bps,
        observed_at_ms=now_ms,
    )


def _process_pending_entries_v21(
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
) -> None:
    def terminal_recorder(
        pending: dict[str, Any],
        *,
        accepted: bool,
        realized_net_pnl: float | None,
    ) -> None:
        _record_v21_pending_outcome(
            stats_db,
            now_ms,
            state,
            pending,
            accepted=accepted,
            realized_net_pnl=realized_net_pnl,
        )

    v20._process_pending_entries_v20(
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
        terminal_outcome_recorder=terminal_recorder,
    )


def _process_maker_probes_v21(
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
) -> None:
    def shadow_recorder(probe: dict[str, Any], **kwargs: Any) -> None:
        _record_v21_shadow_outcome(stats_db, now_ms, probe, **kwargs)

    v20._process_maker_probes_v20(
        state,
        books_by_symbol=books_by_symbol,
        stats_db=stats_db,
        now_ms=now_ms,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        timeout_ms=timeout_ms,
        now_mono_ms=now_mono_ms,
        strict_maker_price_through=strict_maker_price_through,
        shadow_outcome_recorder=shadow_recorder,
        counter_prefix="v21",
        feature_min_samples=8,
        feature_minimum_window_samples=2,
        feature_require_5m_window=False,
        funding_max_hold_seconds=35.0 * 60.0,
        price_discrete_funding=True,
    )


def _refresh_v21_state(state: dict[str, Any]) -> None:
    # Reuse V20's account/funding defaults, then overwrite only V21 identity/policy.
    v20._refresh_v20_state(state)
    state["schema_version"] = SCHEMA_VERSION
    state["portfolio_model"] = PORTFOLIO_MODEL
    state["strategy_id"] = STRATEGY_ID
    state["math_model_revision"] = MATH_MODEL_REVISION
    state["maker_fill_calibration_source"] = "V21_FRESH_COHORT_CAUSAL_SHADOW_ONLY"
    state["execution_acceptance_policy"] = "COHORT_90PCT_CONFIDENCE_BOUND_AND_POSITIVE_CONSERVATIVE_EV"
    state["exit_policy"] = "V21_EARLY_PROFIT_PROTECT_FAST_DIVERGENCE"
    state["target_realized_pnl_per_hour"] = 1.0
    state.setdefault("v21_shadow_accept_count", 0)
    state.setdefault("v21_shadow_reject_count", 0)
    state.setdefault("v21_shadow_nonloss_reject_count", 0)
    state.setdefault("v21_shadow_funding_block_count", 0)
    state.setdefault("v21_nonloss_abort_count", 0)
    state.setdefault("v21_exit_confirmations", {})


def _default_state_v21(
    venue_names: list[str],
    *,
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    state = v20._default_state_v20(
        venue_names,
        initial_equity=initial_equity,
        gross_leverage_cap=gross_leverage_cap,
        max_open_positions=max_open_positions,
    )
    _refresh_v21_state(state)
    return state


def _assert_v21_invariants(state: dict[str, Any]) -> None:
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
            raise ValueError("V21 pending entry maker side is invalid")
    _refresh_v21_state(state)


def load_state_v21(
    path: str | Path,
    *,
    venue_names: list[str],
    initial_equity: float = 100.0,
    gross_leverage_cap: float = 40.0,
    max_open_positions: int = 8,
) -> dict[str, Any]:
    if __package__:
        from .run_arbitrage_paper_v17 import _refresh_v17_margin
    else:
        from run_arbitrage_paper_v17 import _refresh_v17_margin

    state_path = Path(path)
    if not state_path.exists():
        return _default_state_v21(
            venue_names,
            initial_equity=initial_equity,
            gross_leverage_cap=gross_leverage_cap,
            max_open_positions=max_open_positions,
        )
    with state_path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported V21 paper state schema")
    defaults = _default_state_v21(
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
    _refresh_v21_state(state)
    _assert_v21_invariants(state)
    return state


def run_cycle_v21(
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
    else:
        from run_arbitrage_paper_v17 import run_cycle_v17
    from crypto_research.maker_v20 import select_v20_profile

    taker_fees, maker_fees = v20._ensure_v20_runtime_imports()
    state["safety_buffer_bps"] = float(safety_buffer_bps)
    calibration_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def calibration_provider(db_path: str | Path, **kwargs: Any) -> dict[str, Any]:
        return _cycle_v21_calibration_provider(calibration_cache, db_path, **kwargs)

    v20._accrue_v20_continuous_funding(
        state,
        clients=clients,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=journal_path,
    )

    def decide_route(opportunity: ArbitrageOpportunity, **kwargs: Any) -> dict[str, Any]:
        return _v21_route_decision(
            opportunity,
            funding_snapshots=state.get("funding_snapshots", {}),
            now_ms=now_ms,
            attempt_capacity_per_hour=max(1.0, float(max_pending_entries)) * 3600.0 / v20.PENDING_ENTRY_TIMEOUT_SECONDS,
            calibration_provider=calibration_provider,
            **kwargs,
        )

    def process_probes(current_state: dict[str, Any], **kwargs: Any) -> None:
        _process_maker_probes_v21(
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
        pending_entry_processor=_process_pending_entries_v21,
        route_decider=decide_route,
        reprofile_after_reprice=True,
        maker_probe_processor=process_probes,
        invariant_checker=_assert_v21_invariants,
        max_pending_entries=max_pending_entries,
        max_probes=max_probes,
        strategy_id=STRATEGY_ID,
        exit_decision_filter=_confirm_v21_exit,
        exit_decider=v21_exit_decision,
        immediate_exit_reasons={
            "ROUTE_TARGET",
            "PROFIT_PROTECT",
            "DIVERGENCE_STOP",
            "V21_MAX_HOLD",
        },
        monotonic_ms=monotonic_ms,
        per_symbol_history_sampling=True,
        minimum_history_span_ms=420_000,
        minimum_history_samples=8,
        minimum_window_samples=2,
        require_5m_window=False,
        strict_maker_price_through=True,
        route_history_limit=8,
        route_admission_limit=6,
    )
    _refresh_v21_state(state)


def _initialize_v21_runtime(
    *,
    state: dict[str, Any],
    history_db: Path,
    artifacts: Path,
    args: Any,
    symbols: list[str],
    coverage: dict[str, tuple[str, ...]],
) -> None:
    del artifacts, args, coverage
    ensure_v21_execution_schema(history_db)
    interrupted_probes = list(state.get("maker_probes", []))
    state["maker_probes"] = []
    state["maker_probe_restart_discard_count"] = int(
        state.get("maker_probe_restart_discard_count", 0)
    ) + len(interrupted_probes)
    state["v21_capture_buckets"] = ["0_5", "5_10", "10_20", "20_30", "30_40", "40_PLUS"]
    state["v21_symbol_limit"] = len(symbols)
    state["v21_execution_calibration_seeded"] = False
    _refresh_v21_state(state)


def _mark_open_positions_v21(
    state: dict[str, Any], clients: dict[str, Any], *, marked_at_utc: str
) -> None:
    if __package__:
        from .run_arbitrage_paper_v19 import _mark_open_positions_v19
    else:
        from run_arbitrage_paper_v19 import _mark_open_positions_v19

    taker_fees, _ = v20._ensure_v20_runtime_imports()
    _mark_open_positions_v19(
        state,
        clients,
        marked_at_utc=marked_at_utc,
        taker_fee_bps=taker_fees,
    )
    _refresh_v21_state(state)


def _parser_v21():
    parser = v20._parser_v20()
    parser.description = __doc__
    parser.set_defaults(
        symbols=50,
        scan_batch_size=8,
        max_probes=8,
        # ponytail: event-driven books may legitimately be idle; 60s is the hard
        # disconnect backstop until per-stream heartbeat liveness is exposed.
        max_book_age_ms=60_000,
        artifacts_dir=Path("artifacts/arbitrage_v21_live"),
        seed_history_db=Path("artifacts/arbitrage_v20_capacity50/history_v20.sqlite"),
        seed_execution_journal=None,
    )
    return parser


def _validate_v21_args(args: Any) -> None:
    v20._validate_v20_args(args)
    if args.seed_execution_journal is not None:
        raise ValueError("V21 requires fresh cohort execution calibration; do not seed V20/V19 outcomes")


async def _load_v21_universe_activity(
    clients: dict[str, Any],
    coverage: dict[str, tuple[str, ...]],
    *,
    timeout_seconds: float = 8.0,
) -> dict[str, float]:
    """Return public 24h movement scores for equal-coverage universe tie-breaks."""

    import asyncio

    async def fetch(venue: str) -> dict[str, Any]:
        client = clients.get(venue)
        method = getattr(client, "fetch_tickers", None)
        supports = bool((getattr(client, "has", {}) or {}).get("fetchTickers"))
        if client is None or not supports or not callable(method):
            return {}
        try:
            tickers = await asyncio.wait_for(method(), timeout=float(timeout_seconds))
        except Exception:
            # Universe activity is an opportunistic tie-break. Coverage and the
            # deterministic symbol order remain the fail-closed fallback.
            return {}
        return tickers if isinstance(tickers, dict) else {}

    ticker_sets = await asyncio.gather(*(fetch(venue) for venue in ("okx", "gate")))
    scores: dict[str, float] = {}
    for tickers in ticker_sets:
        for symbol in coverage:
            ticker = tickers.get(symbol)
            if not isinstance(ticker, dict):
                continue
            change: float | None = None
            try:
                percentage = float(ticker.get("percentage"))
                if math.isfinite(percentage):
                    change = abs(percentage)
            except (TypeError, ValueError):
                pass
            if change is None:
                try:
                    last = float(ticker.get("last"))
                    opened = float(ticker.get("open"))
                    if math.isfinite(last) and math.isfinite(opened) and last > 0.0 and opened > 0.0:
                        change = abs(last / opened - 1.0) * 100.0
                except (TypeError, ValueError):
                    pass
            if change is not None:
                scores[symbol] = max(change, scores.get(symbol, 0.0))
    return scores


async def _run_v21(args: Any) -> int:
    if __package__:
        from .run_arbitrage_paper_v19 import _run as run_shared
    else:
        from run_arbitrage_paper_v19 import _run as run_shared

    return await run_shared(
        args,
        cycle_runner=run_cycle_v21,
        state_loader=load_state_v21,
        coverage_loader=v20._load_coverage_v20,
        clients_factory=v20.make_public_stream_clients_v20,
        history_filename="history_v21.sqlite",
        health_schema_version=HEALTH_SCHEMA_VERSION,
        state_initializer=_initialize_v21_runtime,
        mark_positions=_mark_open_positions_v21,
        runtime_label="V21",
        runtime_refresher=v20._refresh_funding_snapshots_v20,
        runtime_refresher_background=True,
        runtime_refresher_threaded=True,
        runtime_clients_factory=v20.make_public_funding_clients_v20,
        public_trade_venues=("okx", "gate"),
        universe_activity_loader=_load_v21_universe_activity,
        runtime_refresher_merge_keys=(
            "funding_snapshots",
            "funding_snapshot_error_count",
            "funding_last_full_refresh_ms",
            "funding_full_refresh_count",
            "funding_snapshot_count",
        ),
    )


def main(argv: list[str] | None = None) -> int:
    import asyncio

    args = _parser_v21().parse_args(argv)
    _validate_v21_args(args)
    return asyncio.run(_run_v21(args))


if __name__ == "__main__":
    raise SystemExit(main())
