import pytest

from crypto_research.funding_v20 import (
    accrue_deribit_funding_cashflow,
    accrue_discrete_funding_cashflow,
    pair_funding_admission,
)


def test_carry_observations_keep_equal_quantity_funding_separate_from_pnl(tmp_path):
    import copy
    import sqlite3
    from contextlib import closing
    from crypto_research.funding_v20 import funding_carry_observations, record_carry_observation

    now = 1_000_000
    quotes = {
        "binance|BTC/USDT:USDT": {**_snapshot("binance", 0.001, funding_ts=now + 3600000), "markPrice": 100},
        "okx|BTC/USDT:USDT": {**_snapshot("okx", 0.01, funding_ts=now + 3600000), "markPrice": 102},
        "gate|BTC/USDT:USDT": _snapshot("gate", 0.5, funding_ts=now + 1800000),
        "mexc|BTC/USDT:USDT": _snapshot("mexc", 0.5, funding_ts=now + 3600000, sampled_at_ms=now - 180001),
        "bybit|BTC/USDT:USDT": _snapshot("bybit", float("nan"), funding_ts=now + 3600000),
        "kucoin|BTC/USDT:USDT": _snapshot("kucoin", 1, funding_ts=now - 1),
        "bitget|BTC/USDT:USDT": _snapshot("bitget", 1, funding_ts=now + 3600000, sampled_at_ms=now + 1),
    }
    before = copy.deepcopy(quotes)
    fees = dict.fromkeys(["binance", "okx", "gate", "mexc", "bybit", "kucoin", "bitget"], 5)
    result = funding_carry_observations(quotes, now_ms=now, taker_fee_bps=fees)
    assert result["mode"] == "OBSERVATION_ONLY"
    assert result["fresh_quote_count"] == 3
    assert result["asynchronous_pair_count"] == 4
    assert result["positive_after_fee_quote_count"] == 1
    best = result["rows"][0]
    assert (best["long_venue"], best["short_venue"]) == ("binance", "okx")
    assert best["quoted_funding_bps"] == pytest.approx((.01 * 102 - .001 * 100) / 101 * 10000)
    assert best["round_trip_fee_bps"] == pytest.approx(20)
    assert best["after_fee_quote_bps"] == pytest.approx(best["quoted_funding_bps"] - 20)
    assert best["settlement_at_ms"] == now + 3600000
    assert "realized_pnl" not in result and "expected_value_bps" not in best
    assert quotes["okx|BTC/USDT:USDT"] == before["okx|BTC/USDT:USDT"]
    path = tmp_path / "carry_observations_v22.sqlite"
    record_carry_observation(path, result)
    record_carry_observation(path, result)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM carry_observations_v22").fetchone()[0] == 1
    assert funding_carry_observations(quotes, now_ms=now + 180001, taker_fee_bps=fees)["rows"] == []
    from scripts.publish_monitoring_v13 import load_payload
    from scripts.run_arbitrage_paper_v21 import _default_state_v21
    import json
    from datetime import datetime, timezone

    state = _default_state_v21(["binance", "okx"])
    state["funding_snapshots"] = {key: value for key, value in quotes.items() if key.startswith(("binance|", "okx|"))}
    (tmp_path / "state.json").write_text(json.dumps(state))
    (tmp_path / "health.json").write_text(json.dumps({"status": "HEALTHY"}))
    payload = load_payload(tmp_path, updated_at_utc=datetime.fromtimestamp(now / 1000, timezone.utc).isoformat())
    assert payload["funding_carry_research"]["rows"][0]["after_fee_quote_bps"] > 0
    assert payload["realized_pnl"] == 0 and payload["equity"] == 100
    assert json.loads((tmp_path / "state.json").read_text()) == state


def test_carry_observations_reject_unrepresentable_public_quotes():
    from crypto_research.funding_v20 import funding_carry_observations

    quotes = {"okx|BTC/USDT:USDT": _snapshot("okx", 0.1, funding_ts=float("inf"))}
    assert funding_carry_observations(quotes, now_ms=1000000, taker_fee_bps={"okx": 5})["rows"] == []


def _snapshot(venue, rate, *, funding_ts=None, interval="8h", sampled_at_ms=1_000_000):
    return {
        "venue": venue,
        "fundingRate": rate,
        "fundingTimestamp": funding_ts,
        "interval": interval,
        "sampled_at_ms": sampled_at_ms,
        "markPrice": 100.0,
    }


def test_discrete_funding_window_blocks_entry_before_max_hold_crossing():
    now = 1_000_000
    result = pair_funding_admission(
        long_venue="binance",
        short_venue="okx",
        long_snapshot=_snapshot("binance", 0.0001, funding_ts=now + 30 * 60_000),
        short_snapshot=_snapshot("okx", 0.0001, funding_ts=now + 8 * 60 * 60_000),
        now_ms=now,
        max_hold_seconds=60 * 60,
    )
    assert result["ready"] is True
    assert result["blocked"] is True
    assert result["reason"] == "FUNDING_WINDOW_RISK"


def test_deribit_continuous_funding_uses_eight_hour_time_fraction():
    now = 1_000_000
    result = pair_funding_admission(
        long_venue="deribit",
        short_venue="binance",
        long_snapshot=_snapshot("deribit", 0.0008, funding_ts=None),
        short_snapshot=_snapshot("binance", 0.0001, funding_ts=now + 8 * 60 * 60_000),
        now_ms=now,
        max_hold_seconds=60 * 60,
    )
    assert result["blocked"] is False
    assert result["expected_net_funding_cost_bps"] == pytest.approx(1.0)
    assert result["expected_funding_cost_bps"] == pytest.approx(1.0)


def test_missing_funding_snapshot_blocks_admission_instead_of_assuming_zero():
    result = pair_funding_admission(
        long_venue="binance",
        short_venue="okx",
        long_snapshot=None,
        short_snapshot=_snapshot("okx", 0.0, funding_ts=99_000_000),
        now_ms=1_000_000,
        max_hold_seconds=60 * 60,
    )
    assert result["ready"] is False
    assert result["blocked"] is True
    assert result["reason"] == "FUNDING_DATA_WARMUP"


def test_deribit_realized_funding_cashflow_sign_and_time_fraction():
    # Positive funding: long pays, short receives. 1 hour is 1/8 of the quoted rate.
    assert accrue_deribit_funding_cashflow(
        side="LONG", notional=10_000.0, funding_rate=0.0008, elapsed_seconds=3600
    ) == pytest.approx(-1.0)
    assert accrue_deribit_funding_cashflow(
        side="SHORT", notional=10_000.0, funding_rate=0.0008, elapsed_seconds=3600
    ) == pytest.approx(1.0)


def test_stale_funding_snapshot_fails_closed():
    now = 1_000_000
    stale = _snapshot("binance", 0.0001, funding_ts=now + 8 * 60 * 60_000, sampled_at_ms=now - 181_000)
    result = pair_funding_admission(
        long_venue="binance",
        short_venue="okx",
        long_snapshot=stale,
        short_snapshot=_snapshot("okx", 0.0, funding_ts=now + 8 * 60 * 60_000, sampled_at_ms=now),
        now_ms=now,
        max_hold_seconds=3600,
    )
    assert result["blocked"] is True
    assert result["ready"] is False
    assert result["reason"] == "FUNDING_DATA_WARMUP"


def test_discrete_funding_cashflow_charges_long_and_credits_short_once_per_event():
    assert accrue_discrete_funding_cashflow(
        side="LONG", notional=10_000.0, funding_rate=0.0001
    ) == pytest.approx(-1.0)
    assert accrue_discrete_funding_cashflow(
        side="SHORT", notional=10_000.0, funding_rate=0.0001
    ) == pytest.approx(1.0)


def test_discrete_funding_window_can_be_priced_when_opted_in():
    now = 1_000_000
    result = pair_funding_admission(
        long_venue="binance",
        short_venue="okx",
        long_snapshot=_snapshot("binance", 0.0001, funding_ts=now + 30 * 60_000, sampled_at_ms=now),
        short_snapshot=_snapshot("okx", 0.00005, funding_ts=now + 30 * 60_000, sampled_at_ms=now),
        now_ms=now,
        max_hold_seconds=60 * 60,
        price_discrete_funding=True,
    )
    assert result["ready"] is True
    assert result["blocked"] is False
    assert result["reason"] == "FUNDING_OK"
    assert result["expected_net_funding_cost_bps"] == pytest.approx(0.5)
    assert result["expected_funding_cost_bps"] == pytest.approx(0.5)
