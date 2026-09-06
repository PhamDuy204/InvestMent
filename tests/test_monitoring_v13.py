from __future__ import annotations

import json

import pytest

from crypto_research.monitoring_v13 import build_monitoring_payload, mark_open_position


def _base_state(**overrides):
    state = {
        "initial_equity": 20.0,
        "equity": 20.0,
        "realized_pnl": 0.0,
        "scan_count": 100,
        "opened_position_count": 0,
        "closed_position_count": 0,
        "open_positions": [],
    }
    state.update(overrides)
    return state


def test_payload_keeps_zero_trade_metrics_unknown():
    payload = build_monitoring_payload(
        _base_state(),
        {"status": "HEALTHY", "error": None},
        [],
        updated_at_utc="2026-08-27T09:30:00+00:00",
    )

    assert payload["return_pct"] == 0.0
    assert payload["metrics"]["win_rate_pct"] is None
    assert payload["metrics"]["profit_factor"] is None
    assert payload["metrics"]["max_drawdown_pct"] is None
    assert payload["metrics"]["closed_trade_count"] == 0
    assert set(payload) == {
        "schema_version",
        "updated_at_utc",
        "runner_health",
        "runner_error",
        "initial_equity",
        "equity",
        "realized_pnl",
        "return_pct",
        "scan_count",
        "opened_position_count",
        "closed_position_count",
        "open_position_count",
        "open_positions",
        "closed_positions",
        "metrics",
    }


def test_payload_pairs_open_close_and_calculates_effectiveness():
    events = [
        {
            "record_type": "PAPER_POSITION_OPEN",
            "position_id": "p1",
            "symbol": "BTC/USDT:USDT",
            "long_exchange": "okx",
            "short_exchange": "mexc",
            "quantity": 0.001,
            "opened_at": "2026-08-27T09:00:00+00:00",
            "long_entry_vwap": 100.0,
            "short_entry_vwap": 101.0,
            "entry_fees": 0.02,
            "initial_net_edge_bps": 42.0,
            "apiKey": "must-not-leak",
        },
        {
            "record_type": "PAPER_POSITION_CLOSE",
            "position_id": "p1",
            "symbol": "BTC/USDT:USDT",
            "long_exchange": "okx",
            "short_exchange": "mexc",
            "quantity": 0.001,
            "closed_at": "2026-08-27T09:10:00+00:00",
            "held_seconds": 600.0,
            "close_reason": "CONVERGENCE",
            "remaining_spread_bps": 1.0,
            "long_exit_vwap": 100.5,
            "short_exit_vwap": 100.6,
            "exit_fees": 0.02,
            "gross_pnl": 0.4,
            "realized_net_pnl": 0.36,
            "secret": "must-not-leak",
        },
        {
            "record_type": "PAPER_POSITION_OPEN",
            "position_id": "p2",
            "symbol": "ETH/USDT:USDT",
            "long_exchange": "mexc",
            "short_exchange": "okx",
            "quantity": 0.01,
            "opened_at": "2026-08-27T09:20:00+00:00",
            "long_entry_vwap": 200.0,
            "short_entry_vwap": 201.0,
            "entry_fees": 0.03,
            "initial_net_edge_bps": 30.0,
        },
        {
            "record_type": "PAPER_POSITION_CLOSE",
            "position_id": "p2",
            "symbol": "ETH/USDT:USDT",
            "long_exchange": "mexc",
            "short_exchange": "okx",
            "quantity": 0.01,
            "closed_at": "2026-08-27T09:25:00+00:00",
            "held_seconds": 300.0,
            "close_reason": "MAX_HOLD",
            "remaining_spread_bps": 5.0,
            "long_exit_vwap": 199.8,
            "short_exit_vwap": 201.1,
            "exit_fees": 0.02,
            "gross_pnl": -0.15,
            "realized_net_pnl": -0.20,
            "raw_exchange_response": {"token": "must-not-leak"},
        },
    ]

    payload = build_monitoring_payload(
        _base_state(
            equity=20.16,
            realized_pnl=0.16,
            opened_position_count=2,
            closed_position_count=2,
        ),
        {"status": "HEALTHY", "error": None},
        events,
        updated_at_utc="2026-08-27T09:30:00+00:00",
    )

    metrics = payload["metrics"]
    assert payload["return_pct"] == pytest.approx(0.8)
    assert metrics["win_rate_pct"] == pytest.approx(50.0)
    assert metrics["profit_factor"] == pytest.approx(1.8)
    assert metrics["avg_win"] == pytest.approx(0.36)
    assert metrics["avg_loss"] == pytest.approx(-0.20)
    assert metrics["fee_drag"] == pytest.approx(0.09)
    assert metrics["avg_holding_seconds"] == pytest.approx(450.0)
    assert metrics["max_drawdown_pct"] == pytest.approx((0.20 / 20.36) * 100)
    assert metrics["closed_trade_count"] == 2
    assert metrics["opportunity_to_trade_pct"] is None
    assert payload["closed_positions"][0]["opened_at"] == "2026-08-27T09:00:00+00:00"
    assert payload["closed_positions"][0]["entry_fees"] == pytest.approx(0.02)

    serialized = json.dumps(payload)
    for forbidden in ("apiKey", "secret", "raw_exchange_response", "must-not-leak"):
        assert forbidden not in serialized


def test_open_positions_are_allow_listed_and_runner_error_sanitized():
    state = _base_state(
        open_positions=[
            {
                "position_id": "open-1",
                "position_key": "hidden-internal-key",
                "symbol": "SOL/USDT:USDT",
                "long_exchange": "okx",
                "short_exchange": "mexc",
                "quantity": 1.2,
                "opened_at": "2026-08-27T09:00:00+00:00",
                "long_entry_vwap": 100.0,
                "short_entry_vwap": 101.0,
                "entry_fees": 0.04,
                "initial_net_edge_bps": 22.0,
                "status": "OPEN",
                "secret": "nope",
            }
        ]
    )
    payload = build_monitoring_payload(
        state,
        {"status": "DEGRADED", "error": "venue timeout\nprivate details"},
        [],
        updated_at_utc="2026-08-27T09:30:00+00:00",
    )

    assert payload["open_position_count"] == 1
    assert "position_key" not in payload["open_positions"][0]
    assert "secret" not in payload["open_positions"][0]
    assert payload["runner_error"] == "venue timeout private details"


def test_mark_open_position_uses_executable_close_vwaps_and_all_fees():
    position = {
        "position_id": "open-1",
        "symbol": "BNB/USDT:USDT",
        "long_exchange": "okx",
        "short_exchange": "mexc",
        "quantity": 1.0,
        "opened_at": "2026-08-27T09:00:00+00:00",
        "long_entry_vwap": 100.0,
        "short_entry_vwap": 102.0,
        "long_entry_notional": 100.0,
        "short_entry_notional": 102.0,
        "long_fee_bps": 5.0,
        "short_fee_bps": 8.0,
        "entry_fees": 0.1316,
    }

    mark = mark_open_position(
        position,
        long_book={"bids": [[101.0, 2.0]], "asks": [[101.1, 2.0]]},
        short_book={"bids": [[101.4, 2.0]], "asks": [[101.5, 2.0]]},
        marked_at_utc="2026-08-27T09:10:00+00:00",
    )

    assert mark["mark_status"] == "LIVE"
    assert mark["long_current_vwap"] == pytest.approx(101.0)
    assert mark["short_current_vwap"] == pytest.approx(101.5)
    assert mark["long_unrealized_pnl"] == pytest.approx(1.0)
    assert mark["short_unrealized_pnl"] == pytest.approx(0.5)
    assert mark["gross_unrealized_pnl"] == pytest.approx(1.5)
    assert mark["estimated_exit_fees"] == pytest.approx(0.1317)
    assert mark["estimated_net_pnl_if_closed"] == pytest.approx(1.2367)
    assert mark["current_spread_bps"] == pytest.approx((0.5 / 101.25) * 10_000)
    assert mark["entry_gross_exposure"] == pytest.approx(202.0)
    assert mark["current_gross_exposure"] == pytest.approx(202.5)
    assert mark["held_seconds"] == pytest.approx(600.0)
    assert mark["margin_model"] == "NOT_MODELED"


def test_v14_payload_exposes_modeled_portfolio_risk_and_sanitized_radar():
    state = _base_state(
        schema_version="v14-arbitrage-paper-1",
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="CROSS_MARGIN_OPTIMIZER_V1",
        maintenance_stress_rate=0.05,
        margin_utilization_cap=0.8,
        venue_concentration_penalty_bps=2.0,
        exchange_leverage=2.0,
        gross_leverage_cap=2.0,
        gross_leverage_used=0.5,
        gross_exposure=10.0,
        initial_margin_used=5.0,
        available_margin=15.0,
        max_open_positions=4,
        single_pair_gross_fraction=0.5,
        qualified_opportunity_count=7,
        observed_signal_count=19,
        last_cycle_signal_count=4,
        last_cycle_tradeable_count=1,
        venue_balances={"okx": 10.0, "mexc": 10.0},
        venue_margin_used={"okx": 2.5, "mexc": 2.5},
        venue_available_margin={"okx": 5.5, "mexc": 5.5},
        venue_account_equity={"okx": 10.1, "mexc": 9.9},
        venue_unrealized_pnl={"okx": 0.1, "mexc": -0.1},
        venue_maintenance_stress={"okx": 0.25, "mexc": 0.25},
        venue_margin_ratio={"okx": 40.4, "mexc": 39.6},
        venue_margin_utilization={"okx": 0.2475, "mexc": 0.2525},
        maintenance_stress_used=0.5,
        min_stress_margin_ratio=39.6,
        universe_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        invariant_failure_count=0,
        started_at_utc="2026-08-27T12:00:00+00:00",
        opportunity_radar=[
            {
                "symbol": "BTC/USDT:USDT",
                "available_venues": ["okx", "mexc"],
                "venue_count": 2,
                "decision": "EDGE_BELOW_MIN",
                "buy_venue": "okx",
                "sell_venue": "mexc",
                "gross_edge_bps": 40.0,
                "total_fee_bps": 26.0,
                "safety_buffer_bps": 5.0,
                "best_net_edge_bps": 9.0,
                "signal_status": "TRADEABLE",
                "edge_to_trade_bps": 0.0,
                "optimizer_score_bps": 8.5,
                "optimizer_rank": 1,
                "raw_exchange_response": {"secret": "must-not-leak"},
            }
        ],
        open_positions=[
            {
                "position_id": "v14-open",
                "symbol": "ETH/USDT:USDT",
                "long_exchange": "okx",
                "short_exchange": "mexc",
                "quantity": 0.01,
                "opened_at": "2026-08-27T12:00:00+00:00",
                "long_entry_vwap": 100.0,
                "short_entry_vwap": 102.0,
                "long_entry_notional": 5.0,
                "short_entry_notional": 5.0,
                "long_fee_bps": 5.0,
                "short_fee_bps": 8.0,
                "entry_fees": 0.0065,
                "initial_net_edge_bps": 8.0,
                "margin_model": "CROSS_MARGIN_PAPER_V1",
                "leverage": 2.0,
                "long_initial_margin": 2.5,
                "short_initial_margin": 2.5,
                "initial_margin": 5.0,
                "secret": "must-not-leak",
            }
        ],
    )

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        updated_at_utc="2026-08-27T12:01:00+00:00",
    )

    assert payload["schema_version"] == "v14-monitoring-1"
    assert payload["margin_model"] == "CROSS_MARGIN_PAPER_V1"
    assert payload["portfolio_model"] == "CROSS_MARGIN_OPTIMIZER_V1"
    assert payload["maintenance_stress_rate"] == 0.05
    assert payload["margin_utilization_cap"] == 0.8
    assert payload["venue_account_equity"] == {"okx": 10.1, "mexc": 9.9}
    assert payload["venue_maintenance_stress"] == {"okx": 0.25, "mexc": 0.25}
    assert payload["min_stress_margin_ratio"] == 39.6
    assert payload["exchange_leverage"] == 2.0
    assert payload["gross_leverage_cap"] == 2.0
    assert payload["gross_leverage_used"] == 0.5
    assert payload["initial_margin_used"] == 5.0
    assert payload["venue_available_margin"] == {"okx": 5.5, "mexc": 5.5}
    assert payload["universe_size"] == 2
    assert payload["observed_signal_count"] == 19
    assert payload["last_cycle_signal_count"] == 4
    assert payload["last_cycle_tradeable_count"] == 1
    assert payload["opportunity_radar"][0]["decision"] == "EDGE_BELOW_MIN"
    assert payload["opportunity_radar"][0]["signal_status"] == "TRADEABLE"
    assert payload["opportunity_radar"][0]["edge_to_trade_bps"] == 0.0
    assert payload["opportunity_radar"][0]["available_venues"] == ["okx", "mexc"]
    assert payload["opportunity_radar"][0]["optimizer_score_bps"] == 8.5
    assert payload["opportunity_radar"][0]["optimizer_rank"] == 1
    assert payload["open_positions"][0]["margin_model"] == "CROSS_MARGIN_PAPER_V1"
    assert payload["open_positions"][0]["initial_margin"] == 5.0
    serialized = json.dumps(payload)
    assert "raw_exchange_response" not in serialized
    assert "must-not-leak" not in serialized


def test_v14_live_mark_preserves_modeled_margin_fields():
    position = {
        "position_id": "v14-open",
        "symbol": "BNB/USDT:USDT",
        "long_exchange": "okx",
        "short_exchange": "mexc",
        "quantity": 1.0,
        "opened_at": "2026-08-27T09:00:00+00:00",
        "long_entry_vwap": 100.0,
        "short_entry_vwap": 102.0,
        "long_entry_notional": 100.0,
        "short_entry_notional": 102.0,
        "long_fee_bps": 5.0,
        "short_fee_bps": 8.0,
        "entry_fees": 0.1316,
        "margin_model": "ISOLATED_PAPER_V1",
        "leverage": 2.0,
        "long_initial_margin": 50.0,
        "short_initial_margin": 51.0,
        "initial_margin": 101.0,
    }

    mark = mark_open_position(
        position,
        long_book={"bids": [[101.0, 2.0]], "asks": [[101.1, 2.0]]},
        short_book={"bids": [[101.4, 2.0]], "asks": [[101.5, 2.0]]},
        marked_at_utc="2026-08-27T09:10:00+00:00",
    )

    assert mark["margin_model"] == "ISOLATED_PAPER_V1"


def test_v15_payload_merges_only_allow_listed_shadow_strategy_and_matching_radar_diagnostics():
    state = _base_state(
        schema_version="v14-arbitrage-paper-1",
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="CROSS_MARGIN_OPTIMIZER_V1",
        exchange_leverage=2.0,
        gross_leverage_cap=2.0,
        gross_leverage_used=0.0,
        gross_exposure=0.0,
        initial_margin_used=0.0,
        available_margin=20.0,
        max_open_positions=6,
        single_pair_gross_fraction=0.3,
        qualified_opportunity_count=0,
        observed_signal_count=1,
        last_cycle_signal_count=1,
        last_cycle_tradeable_count=0,
        universe_symbols=["AAA/USDT:USDT"],
        invariant_failure_count=0,
        opportunity_radar=[{
            "symbol": "AAA/USDT:USDT",
            "available_venues": ["cheap", "rich"],
            "venue_count": 2,
            "buy_venue": "cheap",
            "sell_venue": "rich",
            "gross_edge_bps": 16.0,
            "total_fee_bps": 18.0,
            "safety_buffer_bps": 1.0,
            "best_net_edge_bps": -3.0,
            "signal_status": "WATCH",
            "decision": "NO_POSITIVE_EDGE",
        }],
    )
    shadow = {
        "schema_version": "v15-shadow-paper-1",
        "updated_at_utc": "2026-08-27T13:00:00+00:00",
        "strategy_lab": {
            "CONTROL_V14C": {
                "strategy_id": "CONTROL_V14C", "mode": "CONTROL", "realized_pnl": -0.04,
                "open_position_count": 0, "closed_trade_count": 3, "secret": "drop-me",
            },
            "ADAPTIVE_EXIT_SHADOW_V1": {
                "strategy_id": "ADAPTIVE_EXIT_SHADOW_V1", "mode": "SHADOW", "realized_pnl": 0.02,
                "open_position_count": 1, "closed_trade_count": 2, "win_rate_pct": 50.0,
                "profit_factor": 1.5, "raw_positions": ["drop-me"],
            },
            "SPREAD_CONTINUATION_SHADOW_V1": {
                "strategy_id": "SPREAD_CONTINUATION_SHADOW_V1", "mode": "SHADOW", "realized_pnl": -0.01,
                "open_position_count": 0, "closed_trade_count": 1, "win_rate_pct": 0.0,
                "profit_factor": None,
            },
            "FUNDING_AWARE_SHADOW_V1": {
                "strategy_id": "FUNDING_AWARE_SHADOW_V1", "mode": "OBSERVATION_ONLY",
                "observed_route_count": 4,
            },
            "INJECTED": {"strategy_id": "INJECTED", "realized_pnl": 999},
        },
        "radar_diagnostics": {
            "AAA/USDT:USDT": {
                "route": "cheap->rich",
                "persistence_sample_count": 7,
                "persistence_seconds": 1800.0,
                "spread_slope_bps_per_min": 0.2,
                "funding_status": "AVAILABLE",
                "funding_edge_bps": 1.25,
                "secret": "drop-me",
            },
        },
        "secret": "drop-me",
    }

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        shadow_state=shadow,
        updated_at_utc="2026-08-27T13:00:01+00:00",
    )

    assert payload["schema_version"] == "v15-monitoring-1"
    assert payload["shadow_updated_at_utc"] == "2026-08-27T13:00:00+00:00"
    assert [row["strategy_id"] for row in payload["strategy_lab"]] == [
        "CONTROL_V14C",
        "ADAPTIVE_EXIT_SHADOW_V1",
        "SPREAD_CONTINUATION_SHADOW_V1",
        "FUNDING_AWARE_SHADOW_V1",
    ]
    assert payload["strategy_lab"][1]["profit_factor"] == 1.5
    radar = payload["opportunity_radar"][0]
    assert radar["persistence_sample_count"] == 7
    assert radar["persistence_seconds"] == 1800.0
    assert radar["spread_slope_bps_per_min"] == 0.2
    assert radar["funding_edge_bps"] == 1.25
    serialized = json.dumps(payload)
    assert "INJECTED" not in serialized
    assert "secret" not in serialized
    assert "raw_positions" not in serialized
    assert "drop-me" not in serialized


def test_monitoring_radar_drops_nonfinite_numbers() -> None:
    state = _base_state(
        schema_version="v14-arbitrage-paper-1",
        opportunity_radar=[{
            "symbol": "AAA/USDT:USDT",
            "available_venues": ["cheap", "rich"],
            "buy_venue": "cheap",
            "sell_venue": "rich",
            "gross_edge_bps": 12.0,
            "optimizer_score_bps": float("-inf"),
            "best_net_edge_bps": float("nan"),
            "signal_status": "WATCH",
        }],
    )

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        updated_at_utc="2026-08-27T13:00:01+00:00",
    )

    radar = payload["opportunity_radar"][0]
    assert radar["gross_edge_bps"] == 12.0
    assert "optimizer_score_bps" not in radar
    assert "best_net_edge_bps" not in radar
    json.dumps(payload, allow_nan=False)


def test_v16_payload_exposes_only_allow_listed_route_relative_and_monitor_history():
    state = _base_state(
        schema_version="v16-arbitrage-paper-1",
        initial_equity=100.0,
        equity=100.0,
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="ROUTE_RELATIVE_MULTI_STRATEGY_V1",
        maintenance_stress_rate=0.05,
        margin_utilization_cap=0.85,
        venue_concentration_penalty_bps=0.5,
        exchange_leverage=3.0,
        gross_leverage_cap=2.0,
        gross_leverage_used=0.2,
        gross_exposure=20.0,
        initial_margin_used=8.0,
        available_margin=77.0,
        max_open_positions=8,
        single_pair_gross_fraction=0.20,
        qualified_opportunity_count=2,
        observed_signal_count=4,
        last_cycle_signal_count=2,
        last_cycle_tradeable_count=1,
        venue_balances={"cheap": 50.0, "rich": 50.0},
        venue_margin_used={"cheap": 4.0, "rich": 4.0},
        venue_available_margin={"cheap": 38.5, "rich": 38.5},
        venue_account_equity={"cheap": 49.9, "rich": 49.95},
        venue_unrealized_pnl={"cheap": -0.1, "rich": -0.05},
        venue_maintenance_stress={"cheap": 0.5, "rich": 0.5},
        venue_margin_ratio={"cheap": 99.8, "rich": 99.9},
        venue_margin_utilization={"cheap": 0.08, "rich": 0.08},
        maintenance_stress_used=1.0,
        min_stress_margin_ratio=99.8,
        universe_symbols=["AAA/USDT:USDT"],
        invariant_failure_count=0,
        started_at_utc="2026-08-28T00:00:00+00:00",
        open_positions=[{
            "position_id": "p16",
            "symbol": "AAA/USDT:USDT",
            "long_exchange": "cheap",
            "short_exchange": "rich",
            "quantity": 0.1,
            "opened_at": "2026-08-28T00:00:00+00:00",
            "long_entry_vwap": 100.0,
            "short_entry_vwap": 106.0,
            "long_entry_notional": 10.0,
            "short_entry_notional": 10.6,
            "long_fee_bps": 1.0,
            "short_fee_bps": 1.0,
            "entry_fees": 0.00206,
            "initial_net_edge_bps": 35.0,
            "strategy_id": "ROUTE_RELATIVE_MEAN_REVERSION_V1",
            "raw_net_edge_bps": 55.0,
            "entry_baseline_bps": 5.0,
            "entry_excess_spread_bps": 60.0,
            "entry_excess_after_cost_bps": 55.5,
            "entry_fee_hurdle_bps": 4.5,
            "entry_z_score": 3.0,
            "entry_route_sigma_bps": 2.0,
            "entry_short_slope_bps_per_min": -0.2,
            "entry_price_volatility_bps": 10.0,
            "pair_gross_fraction": 0.20,
            "margin_model": "CROSS_MARGIN_PAPER_V1",
            "leverage": 3.0,
            "long_initial_margin": 10.0 / 3.0,
            "short_initial_margin": 10.6 / 3.0,
            "initial_margin": 20.6 / 3.0,
            "secret": "drop-me",
        }],
        opportunity_radar=[{
            "symbol": "AAA/USDT:USDT",
            "available_venues": ["cheap", "rich"],
            "venue_count": 2,
            "buy_venue": "cheap",
            "sell_venue": "rich",
            "gross_edge_bps": 60.0,
            "total_fee_bps": 4.0,
            "safety_buffer_bps": 0.5,
            "best_net_edge_bps": 55.5,
            "baseline_bps": 5.0,
            "route_sigma_bps": 2.0,
            "excess_spread_bps": 55.0,
            "fee_hurdle_bps": 4.5,
            "excess_after_cost_bps": 50.5,
            "z_score": 27.5,
            "short_slope_bps_per_min": -0.2,
            "medium_slope_bps_per_min": 0.4,
            "price_volatility_bps": 10.0,
            "history_sample_count": 50,
            "history_span_seconds": 1800.0,
            "proposed_leverage": 3.0,
            "proposed_pair_gross_fraction": 0.20,
            "proposed_target_notional": 10.0,
            "signal_status": "TRADEABLE",
            "decision": "OPENED",
            "raw_exchange_response": {"secret": "drop-me"},
        }],
    )
    monitor_history = {
        "account_history": [{
            "observed_at_ms": 1_000_000,
            "realized_equity": 100.0,
            "marked_equity": 99.85,
            "realized_pnl": 0.0,
            "unrealized_net_pnl": -0.15,
            "gross_exposure": 20.6,
            "margin_used": 6.87,
            "modeled_fee_drag": 0.004,
            "secret": 999,
        }],
        "position_history": {
            "p16": [{
                "observed_at_ms": 1_000_000,
                "symbol": "AAA/USDT:USDT",
                "spread_bps": 59.0,
                "net_pnl": -0.15,
                "baseline_bps": 5.0,
                "raw": "drop-me",
            }]
        },
    }

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        monitor_history=monitor_history,
        updated_at_utc="2026-08-28T00:00:01+00:00",
    )

    assert payload["schema_version"] == "v16-monitoring-1"
    assert payload["initial_equity"] == 100.0
    assert payload["portfolio_model"] == "ROUTE_RELATIVE_MULTI_STRATEGY_V1"
    position = payload["open_positions"][0]
    assert position["entry_baseline_bps"] == 5.0
    assert position["entry_excess_after_cost_bps"] == 55.5
    assert position["entry_z_score"] == 3.0
    radar = payload["opportunity_radar"][0]
    assert radar["baseline_bps"] == 5.0
    assert radar["excess_after_cost_bps"] == 50.5
    assert radar["proposed_leverage"] == 3.0
    assert payload["account_history"][0]["marked_equity"] == 99.85
    assert payload["position_history"]["p16"][0]["spread_bps"] == 59.0
    serialized = json.dumps(payload, allow_nan=False)
    assert "drop-me" not in serialized
    assert "raw_exchange_response" not in serialized
    assert '"secret"' not in serialized


def test_v17_payload_allow_lists_maker_ev_and_pending_execution_fields():
    state = _base_state(
        schema_version="v17-arbitrage-paper-1",
        initial_equity=100.0,
        equity=100.0,
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="MAKER_FIRST_EV_MULTI_STRATEGY_V1",
        exchange_leverage=3.0,
        gross_leverage_cap=2.0,
        gross_leverage_used=0.0,
        gross_exposure=0.0,
        initial_margin_used=0.0,
        available_margin=100.0,
        max_open_positions=8,
        single_pair_gross_fraction=0.2,
        venue_balances={"okx": 50.0, "bybit": 50.0},
        venue_margin_used={"okx": 0.0, "bybit": 0.0},
        venue_available_margin={"okx": 42.5, "bybit": 42.5},
        venue_account_equity={"okx": 50.0, "bybit": 50.0},
        venue_unrealized_pnl={"okx": 0.0, "bybit": 0.0},
        venue_maintenance_stress={"okx": 0.0, "bybit": 0.0},
        venue_margin_ratio={"okx": 999.0, "bybit": 999.0},
        venue_margin_utilization={"okx": 0.0, "bybit": 0.0},
        universe_symbols=["AAA/USDT:USDT"],
        opportunity_radar=[{
            "symbol": "AAA/USDT:USDT", "buy_venue": "okx", "sell_venue": "bybit",
            "decision": "PASSIVE_TRADEABLE", "gross_edge_bps": 20.0,
            "baseline_60m_bps": 5.0, "baseline_15m_bps": 4.0, "baseline_5m_bps": 3.0,
            "capture_bps": 15.0, "expected_value_bps": 2.2, "minimum_required_ev_bps": 0.4,
            "p_open": 0.6, "p_one_leg": 0.3, "long_fill_probability": 0.7,
            "short_fill_probability": 0.6, "maker_round_trip_hurdle_bps": 8.5,
            "four_taker_hurdle_bps": 21.5, "long_quote_spread_bps": 3.0, "short_quote_spread_bps": 4.0,
            "expected_entry_price_improvement_bps": 4.5, "expected_exit_price_improvement_bps": 4.2, "secret": "nope",
        }],
        pending_entries=[{
            "pending_id": "pending-1", "position_key": "hidden-route-key", "symbol": "AAA/USDT:USDT",
            "long_exchange": "okx", "short_exchange": "bybit", "status": "PENDING_MAKER_ENTRY",
            "placed_at_utc": "2026-08-28T03:00:00+00:00", "long_limit_price": 100.0,
            "short_limit_price": 101.0, "quantity": 0.1, "expected_value_bps": 2.2,
            "p_open": 0.6, "leverage": 2.0, "apiKey": "must-not-leak",
        }],
        pending_exits=[],
        maker_probe_count=12,
        maker_fill_observation_count=20,
        maker_entry_cancel_count=3,
        one_leg_hedge_count=1,
        maker_exit_fallback_count=0,
        maker_hedge_failure_count=0,
        invariant_failure_count=0,
    )
    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        monitor_history={"account_history": [], "position_history": {}},
        updated_at_utc="2026-08-28T03:01:00+00:00",
    )
    assert payload["schema_version"] == "v17-monitoring-1"
    assert payload["portfolio_model"] == "MAKER_FIRST_EV_MULTI_STRATEGY_V1"
    assert payload["pending_entry_count"] == 1
    assert payload["pending_entries"][0]["status"] == "PENDING_MAKER_ENTRY"
    assert "position_key" not in payload["pending_entries"][0]
    assert "apiKey" not in payload["pending_entries"][0]
    radar = payload["opportunity_radar"][0]
    assert radar["expected_value_bps"] == pytest.approx(2.2)
    assert radar["maker_round_trip_hurdle_bps"] == pytest.approx(8.5)
    assert radar["long_quote_spread_bps"] == pytest.approx(3.0)
    assert radar["short_quote_spread_bps"] == pytest.approx(4.0)
    assert radar["expected_entry_price_improvement_bps"] == pytest.approx(4.5)
    assert radar["expected_exit_price_improvement_bps"] == pytest.approx(4.2)
    assert "secret" not in radar
    assert payload["maker_probe_count"] == 12
    assert payload["maker_fill_observation_count"] == 20
    assert "maker_probes" not in payload
    assert "must-not-leak" not in json.dumps(payload)


def test_v18_payload_allow_lists_stream_post_fill_and_actual_execution_fields():
    state = _base_state(
        schema_version="v18-arbitrage-paper-1",
        initial_equity=100.0,
        equity=99.95,
        realized_pnl=-0.05,
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="WS_CAUSAL_POST_FILL_EV_V1",
        exchange_leverage=40.0,
        gross_leverage_cap=40.0,
        open_positions=[{
            "position_id": "p18", "symbol": "AAA/USDT:USDT",
            "long_exchange": "okx", "short_exchange": "bybit", "quantity": 1.0,
            "actual_gross_spread_bps": 22.0, "actual_capture_bps": 8.0,
            "post_fill_expected_value_bps": 1.5, "post_fill_decision": "POST_FILL_EV_ACCEPTED",
            "apiKey": "must-not-leak",
        }],
        pending_entries=[], pending_exits=[], universe_symbols=["AAA/USDT:USDT"],
        post_fill_accept_count=4, post_fill_reject_count=3, both_maker_fill_count=1,
        one_leg_abort_count=3, one_leg_abort_pnl=-0.02, book_update_count=12_345,
        ws_reconnect_count=2, book_cache_entry_count=200, fresh_book_count=190,
        stale_book_count=10, connected_venue_count=7, book_age_ms_median=85.0,
        book_age_ms_max=420, memory_prune_count=6, process_rss_bytes=734_003_200,
        invariant_failure_count=0,
    )

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        monitor_history={"account_history": [], "position_history": {}},
    )

    assert payload["schema_version"] == "v18-monitoring-1"
    assert payload["post_fill_accept_count"] == 4
    assert payload["one_leg_abort_pnl"] == pytest.approx(-0.02)
    assert payload["book_update_count"] == 12_345
    assert payload["book_age_ms_median"] == pytest.approx(85.0)
    assert payload["process_rss_bytes"] == 734_003_200
    assert payload["open_positions"][0]["actual_capture_bps"] == pytest.approx(8.0)
    assert payload["open_positions"][0]["post_fill_decision"] == "POST_FILL_EV_ACCEPTED"
    assert "must-not-leak" not in json.dumps(payload)


def test_payload_marks_stale_healthy_runner_heartbeat():
    payload = build_monitoring_payload(
        _base_state(),
        {
            "status": "HEALTHY",
            "error": None,
            "updated_at_utc": "2026-08-28T09:22:32+00:00",
        },
        [],
        updated_at_utc="2026-08-28T09:23:03+00:00",
    )

    assert payload["runner_health"] == "STALE"


@pytest.mark.parametrize("connected,want", [(6, "DEGRADED"), (7, "HEALTHY")])
def test_v21_monitoring_reflects_expected_venue_coverage(connected, want):
    payload = build_monitoring_payload(
        _base_state(schema_version="v21-arbitrage-paper-1", expected_venue_count=7,
                    connected_venue_count=connected),
        {"status": "HEALTHY", "error": None}, [],
    )
    assert payload["runner_health"] == want
    assert payload["expected_venue_count"] == 7
    assert payload["runner_error"] == ("PUBLIC_VENUE_COVERAGE" if connected < 7 else None)


def test_v21_stale_heartbeat_takes_precedence_over_degraded_coverage():
    payload = build_monitoring_payload(
        _base_state(schema_version="v21-arbitrage-paper-1", expected_venue_count=7,
                    connected_venue_count=6),
        {"status": "DEGRADED", "error": "PUBLIC_VENUE_COVERAGE",
         "updated_at_utc": "2026-09-05T08:00:00+00:00"}, [],
        updated_at_utc="2026-09-05T08:03:00+00:00",
    )
    assert payload["runner_health"] == "STALE"


def test_v21_payload_exposes_current_stream_errors_funding_age_and_account_target():
    payload = build_monitoring_payload(
        _base_state(schema_version="v21-arbitrage-paper-1",
                    target_realized_pnl_per_hour=0.5,
                    funding_last_full_refresh_ms=1788595200000,
                    stream_errors_last_60s_by_venue={"kucoin": 3, "okx": -1}),
        {"status": "HEALTHY"}, [], updated_at_utc="2026-09-05T08:00:30+00:00",
    )
    assert payload.get("target_realized_pnl_per_hour") == 0.5
    assert payload.get("funding_refresh_age_seconds") == 30
    assert payload.get("stream_errors_last_60s_by_venue") == {"kucoin": 3, "okx": 0}


def test_v21_monitoring_allows_periodic_funding_refresh_heartbeat_gap():
    state = _base_state(schema_version="v21-arbitrage-paper-1")
    healthy = build_monitoring_payload(
        state,
        {
            "status": "HEALTHY",
            "error": None,
            "updated_at_utc": "2026-08-31T08:59:00+00:00",
        },
        [],
        updated_at_utc="2026-08-31T08:59:31+00:00",
    )
    stale = build_monitoring_payload(
        state,
        {
            "status": "HEALTHY",
            "error": None,
            "updated_at_utc": "2026-08-31T08:57:00+00:00",
        },
        [],
        updated_at_utc="2026-08-31T08:59:01+00:00",
    )

    assert healthy["runner_health"] == "HEALTHY"
    assert stale["runner_health"] == "STALE"


def test_v19_payload_allow_lists_candidate_funnel_and_stream_causes():
    state = _base_state(
        schema_version="v19-arbitrage-paper-1",
        initial_equity=100.0,
        equity=100.0,
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="WS_CAUSAL_POST_FILL_EV_V2",
        exchange_leverage=40.0,
        gross_leverage_cap=40.0,
        gross_leverage_used=0.0,
        gross_exposure=0.0,
        initial_margin_used=0.0,
        available_margin=100.0,
        max_open_positions=8,
        single_pair_gross_fraction=4.0,
        pending_entries=[{
            "pending_id": "unwind-1",
            "symbol": "AAA/USDT:USDT",
            "long_exchange": "okx",
            "short_exchange": "bybit",
            "quantity": 0.1,
            "placed_at_utc": "2026-08-28T03:00:00+00:00",
            "status": "UNWIND_PENDING",
            "filled_side": "LONG",
            "filled_venue": "okx",
            "cancelled_maker_leg": "SHORT",
            "unwind_reason": "HEDGE_DEPTH_UNAVAILABLE",
            "unwind_pending_since_utc": "2026-08-28T03:00:01+00:00",
            "partial_entry_price": 100.0,
            "partial_entry_notional": 10.0,
            "partial_entry_fee_bps": 2.0,
            "partial_entry_fee": 0.002,
            "partial_gross_notional": 9.99,
            "partial_unrealized_pnl": -0.003,
            "partial_initial_margin": 0.4995,
            "partial_mark_status": "LIVE",
            "unwind_attempt_count": 2,
            "unwind_failure_count": 2,
            "last_unwind_snapshot_at_ms": 123456,
            "apiKey": "must-not-leak",
        }],
        pending_exits=[],
        universe_symbols=["AAA/USDT:USDT"],
        candidate_funnel_counts={
            "observed_route_occurrence": 10,
            "feature_ready_occurrence": 9,
            "ev_qualified_occurrence": 8,
            "unique_candidate": 7,
            "duplicate_rejected": 1,
            "cooldown_rejected": 1,
            "capacity_rejected": 1,
            "margin_rejected": 1,
            "depth_rejected": 1,
            "reprice_ev_rejected": 1,
            "pending_created": 1,
            "no_causal_fill": 2,
            "post_fill_rejected": 1,
            "execution_abort": 2,
            "paired_open": 3,
            "credential-like-secret": 999,
        },
        post_fill_accept_count=4,
        post_fill_reject_count=1,
        both_maker_fill_count=0,
        one_leg_abort_count=1,
        one_leg_abort_pnl=-0.01,
        one_leg_unwind_attempt_count=2,
        one_leg_unwind_failure_count=2,
        partial_exposure_count=1,
        partial_exposure_gross_notional=9.99,
        partial_exposure_unrealized_pnl=-0.003,
        partial_exposure_entry_fees=0.002,
        partial_exposure_reserved_margin=0.4995,
        book_update_count=100,
        ws_reconnect_count=3,
        book_cache_entry_count=25,
        fresh_book_count=20,
        stale_book_count=5,
        age_expired_book_count=2,
        skew_rejected_book_count=0,
        disconnected_book_count=3,
        connected_venue_count=7,
        book_age_ms_median=80.0,
        book_age_ms_max=400,
        memory_prune_count=0,
        process_rss_bytes=500_000_000,
        stream_error_counts={
            "KeyError": 2,
            "RuntimeError": 1,
            "credential-like-secret": 50,
        },
        stream_error_counts_by_venue={
            "gate": {"KeyError": 2, "credential-like-secret": 50},
        },
        raw_exchange_payload={"apiKey": "never-export"},
    )

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        [],
        monitor_history={"account_history": [], "position_history": {}},
    )

    assert payload["schema_version"] == "v19-monitoring-1"
    assert payload["candidate_funnel_counts"]["pending_created"] == 1
    assert payload["candidate_funnel_counts"]["execution_abort"] == 2
    assert "credential-like-secret" not in payload["candidate_funnel_counts"]
    assert payload["partial_exposure_count"] == 1
    assert payload["partial_exposure_gross_notional"] == pytest.approx(9.99)
    assert payload["partial_exposure_reserved_margin"] == pytest.approx(0.4995)
    assert payload["one_leg_unwind_attempt_count"] == 2
    assert payload["one_leg_unwind_failure_count"] == 2
    assert payload["pending_entries"][0]["status"] == "UNWIND_PENDING"
    assert payload["pending_entries"][0]["unwind_reason"] == "HEDGE_DEPTH_UNAVAILABLE"
    assert payload["pending_entries"][0]["unwind_pending_since_utc"] == (
        "2026-08-28T03:00:01+00:00"
    )
    assert payload["pending_entries"][0]["partial_entry_fee"] == pytest.approx(0.002)
    assert payload["pending_entries"][0]["partial_unrealized_pnl"] == pytest.approx(-0.003)
    assert "last_unwind_snapshot_at_ms" not in payload["pending_entries"][0]
    assert "apiKey" not in payload["pending_entries"][0]
    assert payload["age_expired_book_count"] == 2
    assert payload["disconnected_book_count"] == 3
    assert payload["stream_error_counts"] == {"KeyError": 2, "RuntimeError": 1}
    assert payload["stream_error_counts_by_venue"] == {"gate": {"KeyError": 2}}
    serialized = json.dumps(payload)
    assert "credential-like-secret" not in serialized
    assert "never-export" not in serialized


def test_v20_payload_reconciles_account_execution_and_rolling_metrics():
    events = [
        {
            "record_type": "PAPER_POSITION_OPEN",
            "position_id": "p1",
            "opened_at": "2026-08-30T10:00:00+00:00",
            "symbol": "AAA/USDT:USDT",
            "long_exchange": "okx",
            "short_exchange": "kucoin",
            "quantity": 1.0,
        },
        {
            "record_type": "PAPER_POSITION_CLOSE",
            "position_id": "p1",
            "closed_at": "2026-08-30T10:30:00+00:00",
            "symbol": "AAA/USDT:USDT",
            "long_exchange": "okx",
            "short_exchange": "kucoin",
            "quantity": 1.0,
            "entry_fees": 0.02,
            "exit_fees": 0.03,
            "gross_pnl": 0.25,
            "realized_net_pnl": 0.20,
        },
        {
            "record_type": "PAPER_POSITION_OPEN",
            "position_id": "p2",
            "opened_at": "2026-08-30T11:00:00+00:00",
            "symbol": "BBB/USDT:USDT",
            "long_exchange": "bybit",
            "short_exchange": "kucoin",
            "quantity": 1.0,
        },
        {
            "record_type": "PAPER_POSITION_CLOSE",
            "position_id": "p2",
            "closed_at": "2026-08-30T11:30:00+00:00",
            "symbol": "BBB/USDT:USDT",
            "long_exchange": "bybit",
            "short_exchange": "kucoin",
            "quantity": 1.0,
            "entry_fees": 0.01,
            "exit_fees": 0.01,
            "gross_pnl": 0.12,
            "realized_net_pnl": 0.10,
        },
        {
            "record_type": "PAPER_ONE_LEG_ABORT",
            "closed_at": "2026-08-30T12:30:00+00:00",
            "symbol": "CCC/USDT:USDT",
            "filled_side": "LONG",
            "entry_fees": 0.02,
            "exit_fees": 0.03,
            "gross_pnl": -0.15,
            "realized_net_pnl": -0.20,
            "abort_reason": "POST_FILL_EV_REJECTED",
        },
    ]
    state = _base_state(
        schema_version="v20-arbitrage-paper-1",
        initial_equity=100.0,
        equity=100.10,
        realized_pnl=0.10,
        opened_position_count=2,
        closed_position_count=2,
        started_at_utc="2026-08-30T10:00:00+00:00",
        margin_model="CROSS_MARGIN_PAPER_V1",
        portfolio_model="WS_EXECUTION_AWARE_SINGLE_MAKER_V1",
        exchange_leverage=40.0,
        gross_leverage_cap=40.0,
        max_open_positions=8,
        single_pair_gross_fraction=4.0,
        candidate_funnel_counts={},
    )

    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "error": None},
        events,
        updated_at_utc="2026-08-30T13:00:00+00:00",
    )

    assert payload["schema_version"] == "v20-monitoring-1"
    assert payload["paired_realized_pnl"] == pytest.approx(0.30)
    assert payload["non_paired_execution_pnl"] == pytest.approx(-0.20)
    assert payload["account_pnl_reconciliation_error"] == pytest.approx(0.0)
    assert payload["abort_count"] == 1
    assert payload["abort_gross_pnl"] == pytest.approx(-0.15)
    assert payload["abort_fees"] == pytest.approx(0.05)
    assert payload["abort_net_pnl"] == pytest.approx(-0.20)
    assert payload["paired_fee_drag"] == pytest.approx(0.07)
    assert payload["non_paired_fee_drag"] == pytest.approx(0.05)
    assert payload["total_fee_drag"] == pytest.approx(0.12)
    assert payload["runtime_hours"] == pytest.approx(3.0)
    assert payload["paired_trades_per_hour"] == pytest.approx(2 / 3)
    assert payload["paired_pnl_per_hour"] == pytest.approx(0.10)
    assert payload["account_pnl_per_hour"] == pytest.approx(0.10 / 3)
    assert payload["abort_count_per_hour"] == pytest.approx(1 / 3)
    assert payload["abort_loss_per_hour"] == pytest.approx(-0.20 / 3)
    assert payload["rolling_1h_pnl"] == pytest.approx(-0.20)
    assert payload["rolling_3h_pnl"] == pytest.approx(0.10)
    assert payload["rolling_6h_pnl"] == pytest.approx(0.10)
    assert payload["median_entry_gap_seconds"] == pytest.approx(3600.0)
    assert payload["p95_entry_gap_seconds"] == pytest.approx(3600.0)


def test_v20_funding_accrual_reconciles_and_is_included_in_rolling_pnl():
    state = _base_state(
        schema_version="v20-arbitrage-paper-1",
        initial_equity=100.0,
        equity=99.9,
        realized_pnl=-0.1,
        started_at_utc="2026-08-31T00:00:00+00:00",
    )
    events = [
        {
            "record_type": "PAPER_FUNDING_ACCRUAL",
            "position_id": "p1",
            "realized_net_pnl": -0.1,
            "funding_pnl": -0.1,
            "realized_at": "2026-08-31T00:30:00+00:00",
        }
    ]
    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "updated_at_utc": "2026-08-31T00:45:00+00:00"},
        events,
        updated_at_utc="2026-08-31T00:45:00+00:00",
    )
    assert payload["paired_realized_pnl"] == pytest.approx(0.0)
    assert payload["non_paired_execution_pnl"] == pytest.approx(-0.1)
    assert payload["account_pnl_reconciliation_error"] == pytest.approx(0.0)
    assert payload["realized_funding_pnl"] == pytest.approx(-0.1)
    assert payload["funding_pnl_per_hour"] == pytest.approx(-0.1 / 0.75)
    assert payload["rolling_1h_pnl"] == pytest.approx(-0.1)


def test_v21_monitoring_reuses_v20_account_truth_metrics():
    state = _base_state(
        schema_version="v21-arbitrage-paper-1",
        initial_equity=100.0,
        equity=99.9,
        realized_pnl=-0.1,
        started_at_utc="2026-08-31T06:00:00+00:00",
        portfolio_model="WS_COHORT_CALIBRATED_SINGLE_MAKER_V2",
        candidate_funnel_counts={},
        v21_shadow_accept_count=26,
        v21_shadow_reject_count=518,
        public_trade_update_count=4321,
        public_trade_update_counts_by_venue={"okx": 4000, "gate": 321, "secret": 99},
    )
    events = [
        {
            "record_type": "PAPER_ONE_LEG_ABORT",
            "closed_at": "2026-08-31T06:30:00+00:00",
            "symbol": "AAA/USDT:USDT",
            "entry_fees": 0.02,
            "exit_fees": 0.03,
            "gross_pnl": -0.05,
            "realized_net_pnl": -0.10,
        }
    ]
    payload = build_monitoring_payload(
        state,
        {"status": "HEALTHY", "updated_at_utc": "2026-08-31T07:00:00+00:00"},
        events,
        updated_at_utc="2026-08-31T07:00:00+00:00",
    )
    assert payload["schema_version"] == "v21-monitoring-1"
    assert payload["account_pnl_reconciliation_error"] == pytest.approx(0.0)
    assert payload["non_paired_execution_pnl"] == pytest.approx(-0.1)
    assert payload["account_pnl_per_hour"] == pytest.approx(-0.1)
    assert payload["v21_shadow_accept_count"] == 26
    assert payload["v21_shadow_reject_count"] == 518
    assert payload["public_trade_update_count"] == 4321
    assert payload["public_trade_update_counts_by_venue"] == {"okx": 4000, "gate": 321}
