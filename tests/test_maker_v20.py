import json
import sqlite3

import pytest

from crypto_research.maker_v20 import (
    record_v20_execution_outcome,
    seed_v20_execution_outcomes,
    single_maker_attempt_ev,
    v20_execution_calibration,
)


def test_execution_aware_ev_rejects_positive_pair_when_abort_expectancy_is_negative():
    result = single_maker_attempt_ev(
        pair_capture_bps=30.0,
        maker_fee_bps=2.0,
        hedge_taker_fee_bps=6.0,
        expected_exit_fee_bps=10.0,
        expected_exit_price_improvement_bps=2.0,
        maker_quote_improvement_bps=2.0,
        adverse_selection_bps=1.0,
        safety_buffer_bps=0.5,
        fill_probability=0.20,
        expected_funding_cost_bps=0.0,
        minimum_attempt_ev_bps=0.5,
        calibration={
            "ready": True,
            "conservative_accept_probability": 0.20,
            "conservative_reject_net_bps": -25.0,
        },
    )

    assert result["conditional_pair_value_bps"] > 0.0
    assert result["expected_attempt_ev_bps"] < 0.0
    assert result["tradeable"] is False
    assert result["decision"] == "EXECUTION_AWARE_EV_BELOW_MIN"


def test_execution_aware_ev_can_trade_when_accept_probability_covers_reject_tail():
    result = single_maker_attempt_ev(
        pair_capture_bps=40.0,
        maker_fee_bps=2.0,
        hedge_taker_fee_bps=5.0,
        expected_exit_fee_bps=8.0,
        expected_exit_price_improvement_bps=3.0,
        maker_quote_improvement_bps=2.0,
        adverse_selection_bps=1.0,
        safety_buffer_bps=0.5,
        fill_probability=0.20,
        expected_funding_cost_bps=0.0,
        minimum_attempt_ev_bps=0.5,
        calibration={
            "ready": True,
            "conservative_accept_probability": 0.90,
            "conservative_reject_net_bps": -10.0,
        },
    )

    assert result["expected_attempt_ev_bps"] > result["minimum_required_attempt_ev_bps"]
    assert result["tradeable"] is True


def test_execution_calibration_shrinks_sparse_local_acceptance_toward_global(tmp_path):
    db = tmp_path / "history.sqlite"
    for _ in range(8):
        record_v20_execution_outcome(db, venue="binance", side="LONG", accepted=False, reject_net_bps=-24.0)
    for _ in range(2):
        record_v20_execution_outcome(db, venue="binance", side="LONG", accepted=True)
    for _ in range(9):
        record_v20_execution_outcome(db, venue="kucoin", side="SHORT", accepted=False, reject_net_bps=-20.0)
    record_v20_execution_outcome(db, venue="kucoin", side="SHORT", accepted=True)
    # Sparse local 1/1 success must not become q=1.0.
    record_v20_execution_outcome(db, venue="gate", side="LONG", accepted=True)

    calibration = v20_execution_calibration(db, venue="gate", side="LONG")

    assert calibration["global_fill_count"] == 21
    assert calibration["local_fill_count"] == 1
    assert calibration["ready"] is True
    assert 0.0 < calibration["conservative_accept_probability"] < 0.5
    assert calibration["conservative_reject_net_bps"] <= -20.0


def test_seed_execution_outcomes_from_v19_journal_is_idempotent(tmp_path):
    db = tmp_path / "history.sqlite"
    journal = tmp_path / "positions.jsonl"
    records = [
        {
            "record_type": "PAPER_MAKER_ENTRY_PENDING",
            "pending_id": "abort-1",
            "position_key": "AAA|binance|kucoin",
            "long_target_notional": 100.0,
            "short_target_notional": 100.0,
            "placed_at_ms": 1,
        },
        {
            "record_type": "PAPER_ONE_LEG_ABORT",
            "pending_id": "abort-1",
            "position_key": "AAA|binance|kucoin",
            "venue": "binance",
            "filled_side": "LONG",
            "realized_net_pnl": -0.25,
        },
        {
            "record_type": "PAPER_MAKER_ENTRY_PENDING",
            "pending_id": "open-1",
            "position_key": "BBB|bybit|kucoin",
            "long_target_notional": 100.0,
            "short_target_notional": 100.0,
            "placed_at_ms": 2,
        },
        {
            "record_type": "PAPER_POSITION_OPEN",
            "pending_id": "open-1",
            "position_id": "position-1",
            "position_key": "BBB|bybit|kucoin",
            "long_exchange": "bybit",
            "short_exchange": "kucoin",
            "long_entry_liquidity": "MAKER",
            "short_entry_liquidity": "TAKER",
        },
    ]
    journal.write_text("".join(json.dumps(row) + "\n" for row in records))

    assert seed_v20_execution_outcomes(db, journal) == 2
    assert seed_v20_execution_outcomes(db, journal) == 0

    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT venue, side, fill_count, accept_count, reject_count, reject_net_bps_sum "
            "FROM maker_execution_stats_v20 ORDER BY venue, side"
        ).fetchall()
    assert rows == [
        ("binance", "LONG", 1, 0, 1, pytest.approx(-25.0)),
        ("bybit", "LONG", 1, 1, 0, pytest.approx(0.0)),
    ]


def test_v20_profile_keeps_weak_or_risky_attempts_at_20x():
    from crypto_research.maker_v20 import select_v20_profile

    profile = select_v20_profile(
        {
            "expected_attempt_ev_bps": 0.8,
            "minimum_required_ev_bps": 0.5,
            "post_fill_accept_probability": 0.45,
            "conditional_pair_value_bps": 12.0,
            "route_sigma_bps": 4.0,
            "price_volatility_bps": 12.0,
        }
    )
    assert profile["leverage"] == 20.0
    assert profile["pair_gross_fraction"] == 2.0


def test_v20_profile_allows_40x_only_for_high_quality_calibrated_attempt():
    from crypto_research.maker_v20 import select_v20_profile

    profile = select_v20_profile(
        {
            "expected_attempt_ev_bps": 4.0,
            "minimum_required_ev_bps": 0.5,
            "post_fill_accept_probability": 0.80,
            "conditional_pair_value_bps": 25.0,
            "route_sigma_bps": 3.0,
            "price_volatility_bps": 10.0,
        }
    )
    assert profile["leverage"] == 40.0
    assert profile["pair_gross_fraction"] == 4.0


def test_attempt_ev_keeps_fill_probability_in_admission_threshold():
    common = dict(
        pair_capture_bps=20.0,
        maker_fee_bps=2.0,
        hedge_taker_fee_bps=5.0,
        expected_exit_fee_bps=7.0,
        expected_exit_price_improvement_bps=0.0,
        maker_quote_improvement_bps=0.0,
        adverse_selection_bps=1.0,
        safety_buffer_bps=0.0,
        expected_funding_cost_bps=0.0,
        minimum_attempt_ev_bps=0.5,
        calibration={
            "ready": True,
            "conservative_accept_probability": 1.0,
            "conservative_reject_net_bps": -25.0,
        },
    )
    low_fill = single_maker_attempt_ev(fill_probability=0.05, **common)
    high_fill = single_maker_attempt_ev(fill_probability=0.50, **common)

    assert low_fill["expected_attempt_ev_bps"] == pytest.approx(0.25)
    assert low_fill["minimum_required_attempt_ev_bps"] == pytest.approx(0.5)
    assert low_fill["tradeable"] is False
    assert high_fill["expected_attempt_ev_bps"] == pytest.approx(2.5)
    assert high_fill["tradeable"] is True


def test_execution_calibration_uses_stronger_one_sided_lower_bound(tmp_path):
    db = tmp_path / "history.sqlite"
    for _ in range(18):
        record_v20_execution_outcome(db, venue="binance", side="LONG", accepted=False, reject_net_bps=-20.0)
    for _ in range(2):
        record_v20_execution_outcome(db, venue="binance", side="LONG", accepted=True)
    for _ in range(18):
        record_v20_execution_outcome(db, venue="kucoin", side="SHORT", accepted=False, reject_net_bps=-20.0)
    for _ in range(2):
        record_v20_execution_outcome(db, venue="kucoin", side="SHORT", accepted=True)

    calibration = v20_execution_calibration(db, venue="binance", side="LONG")

    # 2/20 local with a 10% global rate and 12 pseudo-observations has shrunk p=10%.
    assert calibration["shrunk_accept_probability"] == pytest.approx(0.10)
    assert calibration["conservative_accept_probability"] < 0.07
    assert calibration["accept_lower_bound_confidence"] == pytest.approx(0.95)


def test_nonloss_reject_counts_as_reject_without_becoming_abort_alpha(tmp_path):
    db = tmp_path / "history.sqlite"
    for _ in range(10):
        record_v20_execution_outcome(db, venue="binance", side="LONG", accepted=False, reject_net_bps=-20.0)
    for _ in range(10):
        record_v20_execution_outcome(db, venue="kucoin", side="SHORT", accepted=False, reject_net_bps=-20.0)
    record_v20_execution_outcome(db, venue="gate", side="LONG", accepted=False, reject_net_bps=3.0)

    calibration = v20_execution_calibration(db, venue="gate", side="LONG")

    assert calibration["local_fill_count"] == 1
    assert calibration["local_reject_count"] == 1
    assert calibration["local_accept_count"] == 0
    assert calibration["conservative_reject_net_bps"] <= 0.0


def test_seed_abort_uses_filled_leg_notional_not_pair_average(tmp_path):
    db = tmp_path / "history.sqlite"
    journal = tmp_path / "positions.jsonl"
    journal.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "record_type": "PAPER_MAKER_ENTRY_PENDING",
                    "pending_id": "abort-long",
                    "position_key": "AAA|binance|kucoin",
                    "long_target_notional": 80.0,
                    "short_target_notional": 120.0,
                    "placed_at_ms": 1,
                },
                {
                    "record_type": "PAPER_ONE_LEG_ABORT",
                    "pending_id": "abort-long",
                    "position_key": "AAA|binance|kucoin",
                    "venue": "binance",
                    "filled_side": "LONG",
                    "realized_net_pnl": -0.20,
                },
            ]
        )
        + "\n"
    )

    assert seed_v20_execution_outcomes(db, journal) == 1
    with sqlite3.connect(db) as connection:
        reject_sum = connection.execute(
            "SELECT reject_net_bps_sum FROM maker_execution_stats_v20"
        ).fetchone()[0]
    assert reject_sum == pytest.approx(-25.0)


def test_seed_nonloss_abort_still_enters_reject_denominator(tmp_path):
    db = tmp_path / "history.sqlite"
    journal = tmp_path / "positions.jsonl"
    journal.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "record_type": "PAPER_MAKER_ENTRY_PENDING",
                    "pending_id": "nonloss-abort",
                    "position_key": "AAA|gate|kucoin",
                    "long_target_notional": 100.0,
                    "short_target_notional": 100.0,
                    "placed_at_ms": 1,
                },
                {
                    "record_type": "PAPER_ONE_LEG_ABORT",
                    "pending_id": "nonloss-abort",
                    "position_key": "AAA|gate|kucoin",
                    "venue": "gate",
                    "filled_side": "LONG",
                    "realized_net_pnl": 0.01,
                },
            ]
        )
        + "\n"
    )

    assert seed_v20_execution_outcomes(db, journal) == 1
    calibration = v20_execution_calibration(db, venue="gate", side="LONG")
    assert calibration["local_fill_count"] == 1
    assert calibration["local_reject_count"] == 1
    with sqlite3.connect(db) as connection:
        reject_sum = connection.execute(
            "SELECT reject_net_bps_sum FROM maker_execution_stats_v20 WHERE venue='gate' AND side='LONG'"
        ).fetchone()[0]
    assert reject_sum == pytest.approx(0.0)
