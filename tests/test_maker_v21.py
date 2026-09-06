import sqlite3

import pytest

from crypto_research.maker_v21 import (
    capture_bucket_v21,
    ensure_v21_execution_schema,
    record_v21_execution_outcome,
    v21_execution_calibration,
    v21_single_maker_attempt_ev,
)


def test_capture_bucket_v21_separates_low_and_high_quality_routes():
    assert capture_bucket_v21(0.0) == "0_5"
    assert capture_bucket_v21(4.999) == "0_5"
    assert capture_bucket_v21(5.0) == "5_10"
    assert capture_bucket_v21(10.0) == "10_20"
    assert capture_bucket_v21(19.999) == "10_20"
    assert capture_bucket_v21(20.0) == "20_30"
    assert capture_bucket_v21(29.999) == "20_30"
    assert capture_bucket_v21(30.0) == "30_40"
    assert capture_bucket_v21(39.999) == "30_40"
    assert capture_bucket_v21(40.0) == "40_PLUS"


def test_v21_calibration_uses_only_matching_capture_cohort_and_keeps_audit_fields(tmp_path):
    db = tmp_path / "history.sqlite"
    # Low-quality fills should not poison the 20+ bps cohort.
    for _ in range(30):
        record_v21_execution_outcome(
            db,
            venue="gate",
            side="LONG",
            placement_capture_bps=3.0,
            post_fill_ev_bps=-12.0,
            accepted=False,
            reject_net_bps=-18.0,
        )
    for _ in range(9):
        record_v21_execution_outcome(
            db,
            venue="gate",
            side="LONG",
            placement_capture_bps=24.0,
            post_fill_ev_bps=8.0,
            accepted=True,
        )
    record_v21_execution_outcome(
        db,
        venue="gate",
        side="LONG",
        placement_capture_bps=24.0,
        post_fill_ev_bps=-2.0,
        accepted=False,
        reject_net_bps=-10.0,
    )

    calibration = v21_execution_calibration(
        db, venue="gate", side="LONG", placement_capture_bps=25.0
    )

    assert calibration["capture_bucket"] == "20_30"
    assert calibration["global_fill_count"] == 10
    assert calibration["global_accept_count"] == 9
    assert calibration["estimated_accept_probability"] == pytest.approx(0.90)
    assert calibration["accept_lower_bound_confidence"] == pytest.approx(0.90)
    assert 0.0 < calibration["conservative_accept_probability"] < 0.90
    assert calibration["ready"] is True
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT placement_capture_bps, post_fill_ev_bps, accepted, reject_net_bps "
            "FROM maker_execution_events_v21 WHERE capture_bucket='20_30' AND accepted=0"
        ).fetchone()
    assert row == pytest.approx((24.0, -2.0, 0, -10.0))


def test_v21_migrates_legacy_20_plus_rows_from_capture_value(tmp_path):
    db = tmp_path / "history.sqlite"
    record_v21_execution_outcome(
        db,
        venue="gate",
        side="LONG",
        placement_capture_bps=44.0,
        post_fill_ev_bps=8.0,
        accepted=True,
    )
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE maker_execution_events_v21 SET capture_bucket='20_PLUS'"
        )

    ensure_v21_execution_schema(db)
    calibration = v21_execution_calibration(
        db, venue="gate", side="LONG", placement_capture_bps=44.0
    )

    assert calibration["capture_bucket"] == "40_PLUS"
    assert calibration["global_fill_count"] == 1
    with sqlite3.connect(db) as connection:
        bucket = connection.execute(
            "SELECT capture_bucket FROM maker_execution_events_v21"
        ).fetchone()[0]
    assert bucket == "40_PLUS"




def test_v21_calibration_missing_db_is_conservative_and_read_only(tmp_path):
    db = tmp_path / "missing.sqlite"

    calibration = v21_execution_calibration(
        db, venue="okx", side="LONG", placement_capture_bps=24.0
    )

    assert db.exists() is False
    assert calibration["ready"] is False
    assert calibration["global_fill_count"] == 0
    assert calibration["conservative_accept_probability"] == pytest.approx(0.0, abs=1e-12)
    assert calibration["conservative_reject_net_bps"] == -25.0

def test_v21_calibration_read_does_not_compete_for_sqlite_write_lock(tmp_path, monkeypatch):
    db = tmp_path / "history.sqlite"
    record_v21_execution_outcome(
        db, venue="okx", side="LONG", placement_capture_bps=24.0,
        post_fill_ev_bps=4.0, accepted=True,
    )
    blocker = sqlite3.connect(db)
    blocker.execute("BEGIN IMMEDIATE")
    original_connect = sqlite3.connect

    def fast_connect(*args, **kwargs):
        kwargs.setdefault("timeout", 0.01)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fast_connect)
    try:
        calibration = v21_execution_calibration(
            db, venue="okx", side="LONG", placement_capture_bps=24.0
        )
    finally:
        blocker.rollback()
        blocker.close()

    assert calibration["global_fill_count"] == 1
    assert calibration["local_fill_count"] == 1

def test_v21_attempt_uses_confidence_bound_and_positive_after_cost_ev():
    common = dict(
        pair_capture_bps=45.0,
        maker_fee_bps=2.0,
        hedge_taker_fee_bps=5.0,
        expected_exit_fee_bps=8.0,
        expected_exit_price_improvement_bps=0.0,
        maker_quote_improvement_bps=2.0,
        adverse_selection_bps=1.0,
        safety_buffer_bps=0.5,
        expected_funding_cost_bps=0.0,
        fill_probability=0.5,
        minimum_attempt_ev_bps=0.25,
    )
    below = v21_single_maker_attempt_ev(
        calibration={
            "ready": True,
            "estimated_accept_probability": 0.899,
            "conservative_accept_probability": 0.80,
            "conservative_reject_net_bps": -10.0,
        },
        **common,
    )
    accepted = v21_single_maker_attempt_ev(
        calibration={
            "ready": True,
            "estimated_accept_probability": 0.90,
            "conservative_accept_probability": 0.80,
            "conservative_reject_net_bps": -10.0,
        },
        **common,
    )
    negative = v21_single_maker_attempt_ev(
        calibration={
            "ready": True,
            "estimated_accept_probability": 0.95,
            "conservative_accept_probability": 0.70,
            "conservative_reject_net_bps": -30.0,
        },
        **{**common, "pair_capture_bps": 18.0},
    )

    assert below["tradeable"] is True
    assert below["decision"] == "V21_RISK_ADJUSTED_EV_ACCEPTED"
    assert accepted["tradeable"] is True
    assert accepted["decision"] == "V21_RISK_ADJUSTED_EV_ACCEPTED"
    assert negative["expected_attempt_ev_bps"] < 0.0
    assert negative["tradeable"] is False


def test_v21_90pct_policy_is_confidence_bound_not_hard_accept_rate_gate():
    decision = v21_single_maker_attempt_ev(
        calibration={
            "ready": True,
            "estimated_accept_probability": 0.50,
            "conservative_accept_probability": 0.45,
            "conservative_reject_net_bps": -5.0,
            "accept_lower_bound_confidence": 0.90,
        },
        pair_capture_bps=45.0,
        maker_fee_bps=2.0,
        hedge_taker_fee_bps=5.0,
        expected_exit_fee_bps=8.0,
        expected_exit_price_improvement_bps=0.0,
        maker_quote_improvement_bps=2.0,
        adverse_selection_bps=1.0,
        safety_buffer_bps=0.5,
        expected_funding_cost_bps=0.0,
        fill_probability=0.5,
        minimum_attempt_ev_bps=0.25,
    )

    assert decision["expected_attempt_ev_bps"] > decision["minimum_required_attempt_ev_bps"]
    assert decision["tradeable"] is True
    assert decision["decision"] == "V21_RISK_ADJUSTED_EV_ACCEPTED"


def test_v21_exit_policy_reacts_sooner_to_extra_entry_risk():
    from crypto_research.maker_v21 import v21_exit_decision

    position = {
        "entry_baseline_bps": 5.0,
        "entry_excess_spread_bps": 20.0,
        "entry_route_sigma_bps": 3.0,
    }
    assert v21_exit_decision(
        position,
        held_seconds=130.0,
        current_spread_bps=20.0,
        close_now_net_pnl=0.02,
        spread_slope_bps_per_min=0.1,
    ) == "PROFIT_PROTECT"
    assert v21_exit_decision(
        position,
        held_seconds=190.0,
        current_spread_bps=31.0,
        close_now_net_pnl=-0.02,
        spread_slope_bps_per_min=0.3,
    ) == "DIVERGENCE_STOP"
    assert v21_exit_decision(
        position,
        held_seconds=30 * 60,
        current_spread_bps=25.0,
        close_now_net_pnl=-0.01,
        spread_slope_bps_per_min=-0.2,
    ) == "V21_MAX_HOLD"


def test_v21_reject_can_audit_missing_post_fill_ev_when_hedge_depth_is_unavailable(tmp_path):
    db = tmp_path / "history.sqlite"
    record_v21_execution_outcome(
        db,
        venue="gate",
        side="LONG",
        placement_capture_bps=22.0,
        post_fill_ev_bps=None,
        accepted=False,
        reject_net_bps=-12.0,
    )
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT post_fill_ev_bps, accepted, reject_net_bps FROM maker_execution_events_v21"
        ).fetchone()
    assert row == (None, 0, -12.0)


def test_v21_calibration_fails_closed_instead_of_crashing_on_transient_sqlite_lock(tmp_path, monkeypatch):
    import crypto_research.maker_v21 as maker_v21

    db = tmp_path / "history.sqlite"
    db.touch()

    def locked_connect(_path):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(maker_v21, "_connect_readonly", locked_connect, raising=False)

    def write_capable_connect_must_not_run(_path):
        raise AssertionError("calibration read must use the read-only connection")

    monkeypatch.setattr(maker_v21, "_connect", write_capable_connect_must_not_run)
    calibration = maker_v21.v21_execution_calibration(
        db, venue="okx", side="LONG", placement_capture_bps=24.0
    )

    assert calibration["ready"] is False
    assert calibration["global_fill_count"] == 0
    assert calibration["local_fill_count"] == 0
    assert calibration["conservative_accept_probability"] == pytest.approx(0.0)
