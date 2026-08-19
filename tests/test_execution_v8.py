from __future__ import annotations

import math

import pandas as pd

from crypto_research.execution_v8 import (
    DelayDamageFit,
    apply_execution_fragility_scale,
    build_delay_damage_labels,
    fit_delay_damage_models,
    gross_exposure_stats,
    lagged_impact_feature,
)


def test_lagged_impact_feature_uses_only_lagged_return_and_quote_volume() -> None:
    frame = pd.DataFrame(
        {
            "lag_return_1h": [0.02, -0.01, 0.0],
            "lag_quote_volume": [1_000_000.0, 2_000_000.0, 0.0],
            "future_return": [999.0, 999.0, 999.0],
        }
    )

    result = lagged_impact_feature(frame)

    assert math.isclose(result.iloc[0], math.log10(0.02 / 1_000_000.0))
    assert math.isclose(result.iloc[1], math.log10(0.01 / 2_000_000.0))
    assert math.isnan(result.iloc[2])


def test_delay_damage_labels_only_charge_exposure_increases() -> None:
    immediate = pd.DataFrame(
        {
            "decision_timestamp": ["2026-01-01T00:00:00Z"] * 3,
            "symbol": ["A", "B", "C"],
            "previous_weight": [0.0, 0.8, -0.3],
            "target_weight": [0.5, 0.3, 0.4],
            "holding_return_label": [0.03, 0.03, 0.04],
            "funding_sum_label": [0.0, 0.0, 0.0],
        }
    )
    delayed = pd.DataFrame(
        {
            "decision_timestamp": ["2026-01-01T00:00:00Z"] * 3,
            "symbol": ["A", "B", "C"],
            "holding_return_label": [0.01, 0.01, 0.01],
            "funding_sum_label": [0.0, 0.0, 0.0],
        }
    )

    labels = build_delay_damage_labels(immediate, delayed).set_index("symbol")

    assert labels.loc["A", "exposure_increase"]
    assert math.isclose(labels.loc["A", "delay_damage_per_unit"], 0.02)
    assert not labels.loc["B", "exposure_increase"]
    assert labels.loc["B", "delay_damage_per_unit"] == 0.0
    assert labels.loc["C", "exposure_increase"]
    assert math.isclose(labels.loc["C", "delay_damage_per_unit"], 0.03)


def test_fit_delay_damage_models_recovers_positive_incremental_impact() -> None:
    selection = pd.DataFrame(
        {
            "lag_rv12": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            "log_impact_1h": [-10.0, -9.0, -8.0, -7.0, -6.0, -5.0],
            "delay_damage_per_unit": [0.001, 0.0025, 0.004, 0.0055, 0.007, 0.0085],
            "exposure_increase": [True] * 6,
        }
    )

    fit = fit_delay_damage_models(selection)

    assert fit.impact_slope > 0.0
    assert fit.anchor_damage > 0.0


def test_execution_fragility_scale_never_boosts_or_blocks_reductions() -> None:
    fit = DelayDamageFit(
        baseline_intercept=0.0,
        baseline_lag_rv_slope=0.0,
        augmented_intercept=0.0,
        augmented_lag_rv_slope=0.0,
        impact_slope=0.01,
        anchor_damage=0.01,
    )
    frame = pd.DataFrame(
        {
            "previous_weight": [0.2, 0.8, -0.3, 0.3],
            "target_weight": [0.8, 0.2, -0.8, -0.5],
            "lag_rv12": [0.0] * 4,
            "log_impact_1h": [2.0] * 4,
        }
    )

    out = apply_execution_fragility_scale(frame, fit)

    assert 0.2 <= out.loc[0, "target_weight"] <= 0.8
    assert -0.8 <= out.loc[2, "target_weight"] <= -0.3
    assert out.loc[1, "target_weight"] == 0.2
    assert -0.5 <= out.loc[3, "target_weight"] <= 0.0
    assert out["execution_fragility_scale"].between(0.0, 1.0).all()


def test_gross_exposure_stats_aggregates_by_decision_timestamp() -> None:
    decisions = pd.DataFrame(
        {
            "decision_timestamp": ["2026-01-01T00:00:00Z"] * 2
            + ["2026-01-01T01:00:00Z"],
            "proposed_target_weight": [0.2, -0.3, 0.1],
        }
    )

    stats = gross_exposure_stats(decisions)

    assert math.isclose(stats["mean_gross_exposure"], 0.3)
    assert math.isclose(stats["median_gross_exposure"], 0.3)
    assert math.isclose(stats["max_gross_exposure"], 0.5)


def test_execution_simulator_walks_book_and_reports_unfilled_tail() -> None:
    from crypto_research.execution_v8 import ExecutionSimulatorV8

    simulator = ExecutionSimulatorV8(fee_bps=4.0)
    book = {"bids": [[99.0, 2.0]], "asks": [[100.0, 1.0], [101.0, 1.0]]}

    result = simulator.simulate_market_order(
        target_notional=250.0,
        side="buy",
        book=book,
        decision_mid=99.5,
        latency_ms=250,
    )

    assert math.isclose(result.filled_notional, 201.0)
    assert math.isclose(result.unfilled_notional, 49.0)
    assert result.unmodeled_tail
    assert result.depth_consumed_levels == 2
    assert math.isclose(result.vwap, 100.5)
    assert result.best_quote == 100.0
    assert result.arrival_mid == 99.5
    assert result.latency_ms == 250
    assert result.total_cost_bps >= result.fee_bps


def test_execution_simulator_partial_level_uses_quote_notional_without_infinite_depth() -> None:
    from crypto_research.execution_v8 import ExecutionSimulatorV8

    simulator = ExecutionSimulatorV8(fee_bps=0.0)
    book = {"bids": [[99.0, 1.0]], "asks": [[101.0, 2.0]]}

    buy = simulator.simulate_market_order(target_notional=50.5, side="buy", book=book)
    sell = simulator.simulate_market_order(target_notional=49.5, side="sell", book=book)

    assert math.isclose(buy.filled_notional, 50.5)
    assert math.isclose(buy.filled_base_quantity, 0.5)
    assert buy.unfilled_notional == 0.0
    assert buy.depth_consumed_levels == 1
    assert math.isclose(sell.filled_notional, 49.5)
    assert math.isclose(sell.filled_base_quantity, 0.5)
    assert sell.unfilled_notional == 0.0


def test_execution_simulator_separates_latency_from_arrival_execution_cost() -> None:
    from crypto_research.execution_v8 import ExecutionSimulatorV8

    simulator = ExecutionSimulatorV8(fee_bps=2.0)
    book = {"bids": [[100.0, 2.0]], "asks": [[102.0, 2.0]]}

    result = simulator.simulate_market_order(
        target_notional=102.0,
        side="buy",
        book=book,
        decision_mid=100.0,
        latency_ms=500,
    )

    assert math.isclose(result.arrival_mid, 101.0)
    assert math.isclose(result.latency_cost_bps, 100.0)
    assert math.isclose(result.spread_cost_bps, (1.0 / 101.0) * 10_000.0)
    assert math.isclose(result.implementation_shortfall_bps, 200.0)
    assert math.isclose(result.total_cost_bps, 202.0)
