from __future__ import annotations

import pytest

from crypto_research.maker_v18 import post_fill_entry_ev, select_v18_profile


def test_post_fill_ev_uses_actual_entry_prices_not_stale_placement_capture():
    result = post_fill_entry_ev(
        long_entry_price=100.0,
        short_entry_price=100.06,
        baseline_60m_bps=5.0,
        baseline_15m_bps=5.0,
        long_entry_fee_bps=2.0,
        short_entry_fee_bps=5.5,
        expected_exit_fee_bps=6.0,
        expected_exit_price_improvement_bps=1.0,
        adverse_selection_bps=0.5,
        route_sigma_bps=3.0,
        price_volatility_bps=8.0,
        safety_buffer_bps=0.5,
        placement_capture_bps=30.0,
    )

    assert result["actual_gross_spread_bps"] == pytest.approx(5.99820054)
    assert result["actual_capture_bps"] == pytest.approx(0.99820054)
    assert result["placement_capture_bps"] == pytest.approx(30.0)
    assert result["post_fill_expected_value_bps"] == pytest.approx(-12.50179946)
    assert result["tradeable"] is False
    assert result["decision"] == "POST_FILL_EV_REJECTED"


def test_post_fill_ev_accepts_actual_capture_after_all_costs():
    result = post_fill_entry_ev(
        long_entry_price=100.0,
        short_entry_price=100.30,
        baseline_60m_bps=5.0,
        baseline_15m_bps=6.0,
        long_entry_fee_bps=2.0,
        short_entry_fee_bps=2.0,
        expected_exit_fee_bps=5.0,
        expected_exit_price_improvement_bps=1.0,
        adverse_selection_bps=0.5,
        route_sigma_bps=2.0,
        price_volatility_bps=5.0,
        safety_buffer_bps=0.5,
        placement_capture_bps=20.0,
    )

    assert result["actual_capture_bps"] > 20.0
    assert result["post_fill_expected_value_bps"] > result["minimum_required_ev_bps"]
    assert result["tradeable"] is True
    assert result["decision"] == "POST_FILL_EV_ACCEPTED"


@pytest.mark.parametrize(
    ("decision", "leverage", "gross_fraction"),
    [
        ({"expected_value_bps": 2.0, "z_score": 1.0, "route_sigma_bps": 9.0, "price_volatility_bps": 40.0}, 20.0, 2.0),
        ({"expected_value_bps": 9.0, "z_score": 2.0, "route_sigma_bps": 6.0, "price_volatility_bps": 25.0}, 30.0, 3.0),
        ({"expected_value_bps": 18.0, "z_score": 3.0, "route_sigma_bps": 3.0, "price_volatility_bps": 12.0}, 40.0, 4.0),
    ],
)
def test_v18_profile_models_ten_percent_pair_margin_without_double_leverage(
    decision, leverage, gross_fraction
):
    profile = select_v18_profile(decision)

    assert profile["leverage"] == leverage
    assert profile["pair_gross_fraction"] == gross_fraction
    assert profile["pair_margin_fraction"] == pytest.approx(0.10)
    assert profile["pair_gross_fraction"] / profile["leverage"] == pytest.approx(0.10)


def test_post_fill_ev_rejects_invalid_prices():
    with pytest.raises(ValueError):
        post_fill_entry_ev(
            long_entry_price=0.0,
            short_entry_price=100.0,
            baseline_60m_bps=5.0,
            baseline_15m_bps=5.0,
            long_entry_fee_bps=2.0,
            short_entry_fee_bps=2.0,
            expected_exit_fee_bps=5.0,
            expected_exit_price_improvement_bps=1.0,
            adverse_selection_bps=0.5,
            route_sigma_bps=2.0,
            price_volatility_bps=5.0,
            safety_buffer_bps=0.5,
            placement_capture_bps=20.0,
        )


def test_v18_profile_accepts_shared_allocator_payload_contract():
    profile = select_v18_profile(
        {
            "excess_after_cost_bps": 9.0,
            "z_score": 2.0,
            "route_sigma_bps": 6.0,
            "price_volatility_bps": 25.0,
        }
    )

    assert profile["leverage"] == 30.0
    assert profile["pair_gross_fraction"] == 3.0
