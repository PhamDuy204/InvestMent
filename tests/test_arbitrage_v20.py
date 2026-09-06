import pytest

from crypto_research.arbitrage_v12 import VenueBook, evaluate_pair
from crypto_research.maker_v20 import v20_execution_calibration
from scripts.run_arbitrage_paper_v17 import _create_pending_entry


def _venue(name, bid, ask, fee=5.0, qty=100.0, timestamp=1_005_000):
    return VenueBook(
        name,
        {
            "bids": [[bid, qty]],
            "asks": [[ask, qty]],
            "timestamp": timestamp,
            "received_at_ms": timestamp,
        },
        fee,
    )


def _state():
    from scripts.run_arbitrage_paper_v19 import _default_state_v19

    return _default_state_v19(["cheap", "rich"])


def _pending(maker_side="LONG", now_ms=1_000_000):
    venues = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=now_ms),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=now_ms),
    }
    pending = _create_pending_entry(
        symbol="AAA/USDT:USDT",
        buy_venue="cheap",
        sell_venue="rich",
        venues=venues,
        target_notional=10.0,
        leverage=20.0,
        pair_gross_fraction=2.0,
        decision={
            "expected_value_bps": 2.0,
            "minimum_required_ev_bps": 0.1,
            "capture_bps": 40.0,
            "baseline_60m_bps": 5.0,
            "baseline_15m_bps": 5.0,
            "baseline_5m_bps": 5.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 3.0,
            "p_open": 0.3,
            "maker_side": maker_side,
            "maker_venue": "cheap" if maker_side == "LONG" else "rich",
            "hedge_venue": "rich" if maker_side == "LONG" else "cheap",
            "post_fill_accept_probability": 0.8,
            "reject_net_bps": -20.0,
            "expected_attempt_ev_bps": 2.0,
        },
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        now_ms=now_ms,
        now_utc="2026-08-30T16:00:00+00:00",
        strategy_id="WS_EXECUTION_AWARE_SINGLE_MAKER_V1",
    )
    return venues, pending


def test_v20_long_maker_ignores_short_maker_touch(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _process_pending_entries_v20

    _, pending = _pending("LONG")
    assert pending["maker_side"] == "LONG"
    state = _state()
    state["pending_entries"] = [pending]
    # Only the SHORT maker price is causally traded through. LONG maker is untouched.
    books = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=1_005_000),
        "rich": _venue("rich", 106.2, 106.3, fee=5.5, timestamp=1_005_000),
    }
    _process_pending_entries_v20(
        state,
        books_by_symbol={"AAA/USDT:USDT": books},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-30T16:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    assert len(state["pending_entries"]) == 1
    assert state["open_positions"] == []


def test_v20_post_fill_reject_records_realized_abort_calibration(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _process_pending_entries_v20

    _, pending = _pending("LONG")
    state = _state()
    state["pending_entries"] = [pending]
    # LONG maker fills, but rich taker hedge has collapsed enough for post-fill rejection.
    books = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=1_005_000),
        "rich": _venue("rich", 99.9, 100.0, fee=5.5, timestamp=1_005_000),
    }
    _process_pending_entries_v20(
        state,
        books_by_symbol={"AAA/USDT:USDT": books},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-30T16:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    calibration = v20_execution_calibration(tmp_path / "history.sqlite", venue="cheap", side="LONG")
    assert calibration["local_reject_count"] == 1
    assert calibration["local_accept_count"] == 0
    assert state["realized_pnl"] < 0.0


def test_v20_post_fill_accept_records_calibration_accept(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _process_pending_entries_v20

    _, pending = _pending("LONG")
    state = _state()
    state["pending_entries"] = [pending]
    books = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=1_005_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=1_005_000),
    }
    _process_pending_entries_v20(
        state,
        books_by_symbol={"AAA/USDT:USDT": books},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-30T16:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    calibration = v20_execution_calibration(tmp_path / "history.sqlite", venue="cheap", side="LONG")
    assert calibration["local_accept_count"] == 1
    assert calibration["local_reject_count"] == 0
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["long_entry_liquidity"] == "MAKER"
    assert state["open_positions"][0]["short_entry_liquidity"] == "TAKER"


def test_v20_route_without_execution_calibration_is_shadow_only(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _v20_route_decision

    venues = {
        "cheap": _venue("cheap", 99.8, 100.0),
        "rich": _venue("rich", 102.0, 102.2, fee=5.5),
    }
    opportunity = evaluate_pair(
        "AAA/USDT:USDT",
        venues["cheap"],
        venues["rich"],
        target_notional=10.0,
        safety_buffer_bps=0.5,
        allow_nonpositive=True,
    )
    assert opportunity is not None
    decision = _v20_route_decision(
        opportunity,
        features={
            "baseline_60m_bps": 100.0,
            "baseline_15m_bps": 100.0,
            "baseline_5m_bps": 100.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 4.0,
        },
        stats_db=tmp_path / "history.sqlite",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots={
            "cheap|AAA/USDT:USDT": {"fundingRate": 0.0, "fundingTimestamp": 29_800_000, "sampled_at_ms": 1_000_000},
            "rich|AAA/USDT:USDT": {"fundingRate": 0.0, "fundingTimestamp": 29_800_000, "sampled_at_ms": 1_000_000},
        },
        now_ms=1_000_000,
    )
    assert decision["tradeable"] is False
    assert decision["decision"] == "EXECUTION_CALIBRATION_WARMUP"
    assert decision["maker_side"] in {"LONG", "SHORT"}


def _seed_route_history(db, *, symbol, buy_venue, sell_venue, now_ms, gross=5.0):
    from crypto_research.route_v16 import record_route_snapshots

    start = now_ms - 20 * 60_000
    for i in range(80):
        record_route_snapshots(
            db,
            start + i * 15_000,
            [
                {
                    "symbol": symbol,
                    "buy_venue": buy_venue,
                    "sell_venue": sell_venue,
                    "gross_edge_bps": gross,
                    "reference_mid_price": 100.0,
                }
            ],
        )


def test_v20_shadow_causal_fill_calibrates_without_equity_mutation(tmp_path):
    from scripts.run_arbitrage_paper_v17 import _probe_from_route
    from scripts.run_arbitrage_paper_v20 import _process_maker_probes_v20

    symbol = "SHADOW/USDT:USDT"
    placed_ms = 2_000_000
    venues = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=placed_ms),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms),
    }
    opportunity = evaluate_pair(
        symbol,
        venues["cheap"],
        venues["rich"],
        target_notional=10.0,
        safety_buffer_bps=0.5,
        allow_nonpositive=True,
    )
    assert opportunity is not None
    probe = _probe_from_route(opportunity, venues, now_ms=placed_ms)
    state = _state()
    state["maker_probes"] = [probe]
    state["funding_snapshots"] = {
        f"cheap|{symbol}": {
            **_funding_snapshot(0.0, funding_ts=placed_ms + 8 * 60 * 60_000),
            "sampled_at_ms": placed_ms + 5_000,
        },
        f"rich|{symbol}": {
            **_funding_snapshot(0.0, funding_ts=placed_ms + 8 * 60 * 60_000),
            "sampled_at_ms": placed_ms + 5_000,
        },
    }
    before_equity = state["equity"]
    before_balances = dict(state["venue_balances"])
    db = tmp_path / "history.sqlite"
    _seed_route_history(
        db,
        symbol=symbol,
        buy_venue="cheap",
        sell_venue="rich",
        now_ms=placed_ms + 5_000,
    )
    later = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=placed_ms + 5_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms + 5_000),
    }
    _process_maker_probes_v20(
        state,
        books_by_symbol={symbol: later},
        stats_db=db,
        now_ms=placed_ms + 5_000,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    calibration = v20_execution_calibration(db, venue="cheap", side="LONG")
    assert calibration["local_accept_count"] == 1
    assert state["maker_probes"] == []
    assert state["equity"] == before_equity
    assert state["venue_balances"] == before_balances
    assert state["realized_pnl"] == 0.0


def test_v20_shadow_timeout_does_not_fake_execution_outcome(tmp_path):
    from scripts.run_arbitrage_paper_v17 import _probe_from_route
    from scripts.run_arbitrage_paper_v20 import _process_maker_probes_v20

    symbol = "NOFILL/USDT:USDT"
    placed_ms = 3_000_000
    venues = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=placed_ms),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms),
    }
    opportunity = evaluate_pair(
        symbol,
        venues["cheap"],
        venues["rich"],
        target_notional=10.0,
        safety_buffer_bps=0.5,
        allow_nonpositive=True,
    )
    assert opportunity is not None
    state = _state()
    state["maker_probes"] = [_probe_from_route(opportunity, venues, now_ms=placed_ms)]
    db = tmp_path / "history.sqlite"
    unchanged = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=placed_ms + 21_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms + 21_000),
    }
    _process_maker_probes_v20(
        state,
        books_by_symbol={symbol: unchanged},
        stats_db=db,
        now_ms=placed_ms + 21_000,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    calibration = v20_execution_calibration(db, venue="cheap", side="LONG")
    assert calibration["global_fill_count"] == 0
    assert state["maker_probes"] == []


def test_v20_shadow_timeout_drops_unavailable_probe_without_fake_outcome(tmp_path):
    from scripts.run_arbitrage_paper_v17 import _probe_from_route
    from scripts.run_arbitrage_paper_v20 import _process_maker_probes_v20

    symbol = "ORPHAN/USDT:USDT"
    placed_ms = 4_000_000
    venues = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=placed_ms),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms),
    }
    opportunity = evaluate_pair(
        symbol,
        venues["cheap"],
        venues["rich"],
        target_notional=10.0,
        safety_buffer_bps=0.5,
        allow_nonpositive=True,
    )
    assert opportunity is not None
    state = _state()
    state["maker_probes"] = [
        _probe_from_route(opportunity, venues, now_ms=placed_ms)
    ]
    before_observation_count = int(state.get("maker_fill_observation_count", 0))
    db = tmp_path / "history.sqlite"

    _process_maker_probes_v20(
        state,
        books_by_symbol={},
        stats_db=db,
        now_ms=placed_ms + 21_000,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )

    calibration = v20_execution_calibration(db, venue="cheap", side="LONG")
    assert state["maker_probes"] == []
    assert calibration["global_fill_count"] == 0
    assert int(state.get("maker_fill_observation_count", 0)) == before_observation_count


def test_v20_stable_swap_filter_accepts_exact_usdc_settlement_only():
    from scripts.run_arbitrage_paper_v20 import _eligible_linear_stable_swap

    assert _eligible_linear_stable_swap(
        {"swap": True, "linear": True, "quote": "USDC", "settle": "USDC", "active": True}
    )
    assert not _eligible_linear_stable_swap(
        {"swap": True, "linear": True, "quote": "USDT", "settle": "USDC", "active": True}
    )
    assert not _eligible_linear_stable_swap(
        {"swap": True, "linear": True, "quote": "USD", "settle": "USD", "active": True}
    )


def test_v20_fee_model_uses_verified_deribit_and_gate_base_tiers():
    from scripts.run_arbitrage_paper_v20 import _ensure_v20_runtime_imports

    taker, maker = _ensure_v20_runtime_imports()
    assert (maker["deribit"], taker["deribit"]) == (1.5, 3.5)
    assert (maker["gate"], taker["gate"]) == (2.0, 5.0)


def _funding_snapshot(rate=0.0, *, funding_ts=99_000_000):
    return {
        "fundingRate": rate,
        "fundingTimestamp": funding_ts,
        "nextFundingTimestamp": funding_ts,
        "interval": "8h",
        "sampled_at_ms": 1_000_000,
    }


def test_v20_route_fails_closed_when_funding_data_is_missing(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _v20_route_decision

    venues = {
        "cheap": _venue("cheap", 99.8, 100.0),
        "rich": _venue("rich", 102.0, 102.2, fee=5.5),
    }
    opportunity = evaluate_pair(
        "AAA/USDT:USDT", venues["cheap"], venues["rich"],
        target_notional=10.0, safety_buffer_bps=0.5, allow_nonpositive=True,
    )
    assert opportunity is not None
    decision = _v20_route_decision(
        opportunity,
        features={
            "baseline_60m_bps": 100.0,
            "baseline_15m_bps": 100.0,
            "baseline_5m_bps": 100.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 4.0,
        },
        stats_db=tmp_path / "history.sqlite",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots={},
        now_ms=1_000_000,
    )
    assert decision["tradeable"] is False
    assert decision["decision"] == "FUNDING_DATA_WARMUP"


def test_v20_route_blocks_discrete_funding_inside_max_hold(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _v20_route_decision

    symbol = "AAA/USDT:USDT"
    venues = {
        "cheap": _venue("cheap", 99.8, 100.0),
        "rich": _venue("rich", 102.0, 102.2, fee=5.5),
    }
    opportunity = evaluate_pair(
        symbol, venues["cheap"], venues["rich"],
        target_notional=10.0, safety_buffer_bps=0.5, allow_nonpositive=True,
    )
    assert opportunity is not None
    now = 1_000_000
    funding = {
        f"cheap|{symbol}": _funding_snapshot(funding_ts=now + 30 * 60_000),
        f"rich|{symbol}": _funding_snapshot(funding_ts=now + 8 * 60 * 60_000),
    }
    decision = _v20_route_decision(
        opportunity,
        features={
            "baseline_60m_bps": 100.0,
            "baseline_15m_bps": 100.0,
            "baseline_5m_bps": 100.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 4.0,
        },
        stats_db=tmp_path / "history.sqlite",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots=funding,
        now_ms=now,
    )
    assert decision["tradeable"] is False
    assert decision["decision"] == "FUNDING_WINDOW_RISK"


def test_v20_refreshes_public_funding_snapshots_without_credentials():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class FundingClient:
        def __init__(self, rate):
            self.rate = rate
            self.calls = []

        async def fetch_funding_rate(self, symbol):
            self.calls.append(symbol)
            return {
                "symbol": symbol,
                "fundingRate": self.rate,
                "fundingTimestamp": 9_000_000,
                "nextFundingTimestamp": 37_800_000,
                "interval": "8h",
            }

    clients = {"cheap": FundingClient(0.0001), "rich": FundingClient(-0.0002)}
    state = {}
    symbol = "AAA/USDT:USDT"
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients=clients,
            state=state,
            symbols=[symbol],
            coverage={symbol: ("cheap", "rich")},
            now_ms=1_000_000,
        )
    )

    assert clients["cheap"].calls == [symbol]
    assert clients["rich"].calls == [symbol]
    assert state["funding_snapshots"][f"cheap|{symbol}"]["fundingRate"] == 0.0001
    assert state["funding_snapshots"][f"rich|{symbol}"]["fundingRate"] == -0.0002
    assert state["funding_snapshot_error_count"] == 0


def test_v20_exact_reprice_downgrades_leverage_before_pending_creation(tmp_path):
    from scripts.run_arbitrage_paper_v17 import _default_state_v17, run_cycle_v17

    class Client:
        def __init__(self, book):
            self.book = book
        def fetch_order_book(self, symbol, limit=None):
            del symbol, limit
            return self.book

    symbol = "PROFILE/USDT:USDT"
    now = 7_000_000
    clients = {
        "cheap": Client({"bids": [[99.9, 100.0]], "asks": [[100.0, 100.0]], "timestamp": now}),
        "rich": Client({"bids": [[102.0, 100.0]], "asks": [[102.1, 100.0]], "timestamp": now}),
    }
    route_calls = 0

    def route_decider(opportunity, **kwargs):
        nonlocal route_calls
        del kwargs
        if opportunity.buy_venue != "cheap":
            return {"tradeable": False, "decision": "NO"}
        route_calls += 1
        ev = 5.0 if route_calls == 1 else 1.0
        return {
            "tradeable": True,
            "decision": "OK",
            "expected_value_bps": ev,
            "expected_attempt_ev_bps": ev,
            "minimum_required_ev_bps": 0.5,
            "capture_bps": 20.0,
            "z_score": 3.0,
            "baseline_60m_bps": 1.0,
            "baseline_15m_bps": 1.0,
            "baseline_5m_bps": 1.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 3.0,
            "p_open": 0.5,
            "post_fill_accept_probability": 0.8,
            "conditional_pair_value_bps": 25.0 if ev == 5.0 else 10.0,
        }

    def profile(decision):
        high = float(decision["expected_value_bps"]) >= 5.0
        leverage = 40.0 if high else 20.0
        return {
            "leverage": leverage,
            "pair_margin_fraction": 0.10,
            "pair_gross_fraction": leverage * 0.10,
        }

    state = _default_state_v17(list(clients), gross_leverage_cap=40.0)
    state["min_position_leverage"] = 20.0
    state["max_position_leverage"] = 40.0
    run_cycle_v17(
        clients=clients,
        symbols=[symbol],
        state=state,
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.0},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=now,
        now_utc="2026-08-31T00:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={symbol: ("cheap", "rich")},
        route_decider=route_decider,
        profile_selector=profile,
        reprofile_after_reprice=True,
        max_probes=0,
    )

    assert len(state["pending_entries"]) == 1
    assert state["pending_entries"][0]["leverage"] == 20.0
    assert state["pending_entries"][0]["pair_gross_fraction"] == 2.0


def test_v20_deribit_funding_accrual_mutates_equity_and_journal_once_per_interval(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _accrue_v20_continuous_funding

    class Client:
        def fetch_order_book(self, symbol, limit=None):
            del symbol, limit
            return {"bids": [[99.9, 100.0]], "asks": [[100.1, 100.0]]}

    state = {
        "venue_balances": {"deribit": 50.0, "other": 50.0},
        "equity": 100.0,
        "realized_pnl": 0.0,
        "realized_funding_pnl": 0.0,
        "funding_snapshots": {
            "deribit|AAA/USDC:USDC": {
                "fundingRate": 0.0008,
                "markPrice": 100.0,
                "sampled_at_ms": 1_060_000,
            }
        },
        "open_positions": [
            {
                "position_id": "p1",
                "symbol": "AAA/USDC:USDC",
                "long_exchange": "deribit",
                "short_exchange": "other",
                "quantity": 100.0,
                "opened_at_ms": 1_000_000,
                "funding_last_accrual_ms": 1_000_000,
                "long_funding_rate": 0.0008,
                "long_funding_mark_price": 100.0,
            }
        ],
    }
    journal = tmp_path / "positions.jsonl"

    _accrue_v20_continuous_funding(
        state,
        clients={"deribit": Client()},
        now_ms=1_060_000,
        now_utc="2026-08-31T00:01:00+00:00",
        journal_path=journal,
    )

    expected = -10_000.0 * 0.0008 / 480.0
    assert state["venue_balances"]["deribit"] == pytest.approx(50.0 + expected)
    assert state["equity"] == pytest.approx(100.0 + expected)
    assert state["realized_pnl"] == pytest.approx(expected)
    assert state["realized_funding_pnl"] == pytest.approx(expected)
    event = __import__("json").loads(journal.read_text().strip())
    assert event["record_type"] == "PAPER_FUNDING_ACCRUAL"
    assert event["realized_net_pnl"] == pytest.approx(expected)
    assert event["funding_rate"] == pytest.approx(0.0008)

    # A second cycle inside the minute must not double-accrue.
    _accrue_v20_continuous_funding(
        state,
        clients={"deribit": Client()},
        now_ms=1_070_000,
        now_utc="2026-08-31T00:01:10+00:00",
        journal_path=journal,
    )
    assert len(journal.read_text().strip().splitlines()) == 1


def test_v20_nonloss_realized_reject_still_enters_reject_denominator(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v20 as v20

    _, pending = _pending("LONG")
    state = _state()
    state["pending_entries"] = [pending]

    def fake_processor(current_state, **kwargs):
        kwargs["execution_outcome_recorder"](
            current_state["pending_entries"][0],
            accepted=False,
            realized_net_pnl=0.01,
        )
        current_state["pending_entries"] = []

    monkeypatch.setattr(v20, "_process_pending_entries_v19", fake_processor)
    db = tmp_path / "history.sqlite"
    v20._process_pending_entries_v20(
        state,
        books_by_symbol={},
        stats_db=db,
        now_ms=1_005_000,
        now_utc="2026-08-31T00:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
    )
    calibration = v20_execution_calibration(db, venue="cheap", side="LONG")
    assert calibration["local_fill_count"] == 1
    assert calibration["local_reject_count"] == 1
    assert calibration["local_accept_count"] == 0
    assert state["v20_nonloss_abort_count"] == 1


def test_v20_funding_refresh_batches_when_exchange_supports_bulk_endpoint():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class BatchClient:
        has = {"fetchFundingRates": True, "fetchFundingRate": True}
        def __init__(self):
            self.batch_calls = []
            self.single_calls = []
        async def fetch_funding_rates(self, symbols):
            self.batch_calls.append(tuple(symbols))
            return {
                symbol: {
                    "symbol": symbol,
                    "fundingRate": 0.0001,
                    "fundingTimestamp": 99_000_000,
                    "interval": "8h",
                }
                for symbol in symbols
            }
        async def fetch_funding_rate(self, symbol):
            self.single_calls.append(symbol)
            raise AssertionError("bulk-capable client should not use single endpoint")

    symbols = ["A/USDT:USDT", "B/USDT:USDT"]
    client = BatchClient()
    state = {}
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"okx": client},
            state=state,
            symbols=symbols,
            coverage={symbol: ("okx",) for symbol in symbols},
            now_ms=1_000_000,
        )
    )
    assert client.batch_calls == [tuple(symbols)]
    assert client.single_calls == []
    assert len(state["funding_snapshots"]) == 2


def test_v20_deribit_accrual_uses_previous_causal_funding_mark_not_future_book_mid(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _accrue_v20_continuous_funding

    class Client:
        def fetch_order_book(self, symbol, limit=None):
            del symbol, limit
            return {"bids": [[199.9, 100.0]], "asks": [[200.1, 100.0]]}

    state = {
        "venue_balances": {"deribit": 50.0, "other": 50.0},
        "equity": 100.0,
        "realized_pnl": 0.0,
        "realized_funding_pnl": 0.0,
        "funding_snapshots": {
            "deribit|AAA/USDC:USDC": {
                "fundingRate": 0.0004,
                "markPrice": 200.0,
                "sampled_at_ms": 1_060_000,
            }
        },
        "open_positions": [
            {
                "position_id": "p1",
                "symbol": "AAA/USDC:USDC",
                "long_exchange": "deribit",
                "short_exchange": "other",
                "quantity": 100.0,
                "opened_at_ms": 1_000_000,
                "funding_last_accrual_ms": 1_000_000,
                "long_funding_rate": 0.0008,
                "long_funding_mark_price": 100.0,
            }
        ],
    }
    journal = tmp_path / "funding.jsonl"
    _accrue_v20_continuous_funding(
        state,
        clients={"deribit": Client()},
        now_ms=1_060_000,
        now_utc="2026-08-31T00:01:00+00:00",
        journal_path=journal,
    )
    # Past minute uses the last-known 100 USDC mark and 0.0008 rate, not the new 200 mark.
    expected = -(100.0 * 100.0) * 0.0008 / 480.0
    assert state["realized_funding_pnl"] == pytest.approx(expected)
    position = state["open_positions"][0]
    assert position["long_funding_rate"] == pytest.approx(0.0004)
    assert position["long_funding_mark_price"] == pytest.approx(200.0)


def test_v20_post_fill_revalidation_subtracts_expected_funding_cost(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v19 as v19
    from scripts.run_arbitrage_paper_v20 import _process_pending_entries_v20

    _, pending = _pending("LONG")
    pending["expected_funding_cost_bps"] = 1.0
    state = _state()
    state["pending_entries"] = [pending]
    books = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=1_005_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=1_005_000),
    }

    monkeypatch.setattr(
        v19,
        "post_fill_entry_ev",
        lambda **kwargs: {
            "actual_gross_spread_bps": 20.0,
            "actual_capture_bps": 10.0,
            "post_fill_expected_value_bps": 1.0,
            "minimum_required_ev_bps": 0.5,
            "decision": "POST_FILL_EV_ACCEPTED",
            "tradeable": True,
        },
    )
    _process_pending_entries_v20(
        state,
        books_by_symbol={"AAA/USDT:USDT": books},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-31T00:00:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    assert state["open_positions"] == []
    assert state["realized_pnl"] < 0.0
    calibration = v20_execution_calibration(tmp_path / "history.sqlite", venue="cheap", side="LONG")
    assert calibration["local_reject_count"] == 1


def test_v20_attempt_floor_is_derived_from_account_hourly_target(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v20 as v20

    monkeypatch.setattr(
        v20,
        "conservative_fill_probability",
        lambda *args, **kwargs: {"conservative_probability": 0.5, "attempts": 100, "fills": 50},
    )
    monkeypatch.setattr(
        v20,
        "v20_execution_calibration",
        lambda *args, **kwargs: {
            "ready": True,
            "conservative_accept_probability": 1.0,
            "conservative_reject_net_bps": -25.0,
            "global_fill_count": 100,
            "local_fill_count": 50,
        },
    )
    symbol = "AAA/USDT:USDT"
    venues = {
        "cheap": _venue("cheap", 99.8, 100.0),
        "rich": _venue("rich", 102.0, 102.2, fee=5.5),
    }
    opportunity = evaluate_pair(
        symbol, venues["cheap"], venues["rich"],
        target_notional=2.0, safety_buffer_bps=0.5, allow_nonpositive=True,
    )
    assert opportunity is not None
    now = 1_000_000
    funding = {
        f"cheap|{symbol}": _funding_snapshot(funding_ts=now + 8 * 60 * 60_000),
        f"rich|{symbol}": _funding_snapshot(funding_ts=now + 8 * 60 * 60_000),
    }
    decision = v20._v20_route_decision(
        opportunity,
        features={
            "baseline_60m_bps": 100.0,
            "baseline_15m_bps": 100.0,
            "baseline_5m_bps": 100.0,
            "route_sigma_bps": 0.5,
            "price_volatility_bps": 0.0,
        },
        stats_db=tmp_path / "history.sqlite",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots=funding,
        now_ms=now,
        attempt_capacity_per_hour=240.0,
    )
    minimum_dollars = 0.05 / 240.0
    assert decision["minimum_required_attempt_dollars"] >= minimum_dollars - 1e-12
    assert decision["minimum_required_ev_bps"] == pytest.approx(
        decision["minimum_required_attempt_dollars"] / opportunity.target_notional * 10_000.0
    )
    assert decision["expected_attempt_dollars"] == pytest.approx(
        decision["expected_attempt_ev_bps"] / 10_000.0 * opportunity.target_notional
    )


def test_v20_shadow_post_fill_uses_same_funding_cost_as_production(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v20 as v20
    from crypto_research.route_v16 import record_route_snapshots

    now = 2_000_000
    symbol = "AAA/USDC:USDC"
    probe = {
        "probe_id": "funding-shadow",
        "position_key": f"{symbol}|deribit|rich",
        "symbol": symbol,
        "long_exchange": "deribit",
        "short_exchange": "rich",
        "long_limit_price": 100.0,
        "short_limit_price": 102.0,
        "target_notional": 10.0,
        "quantity": 0.1,
        "placed_at_ms": now - 5_000,
    }
    state = _state()
    state["maker_probes"] = [probe]
    state["funding_snapshots"] = {
        f"deribit|{symbol}": {
            "fundingRate": 0.008,
            "fundingTimestamp": None,
            "nextFundingTimestamp": None,
            "interval": "8h",
            "markPrice": 100.0,
            "sampled_at_ms": now,
        },
        f"rich|{symbol}": {
            **_funding_snapshot(0.0, funding_ts=now + 8 * 60 * 60_000),
            "sampled_at_ms": now,
        },
    }
    db = tmp_path / "history.sqlite"
    # Enough causal route history for shadow post-fill evaluation.
    for stamp in range(now - 900_000, now + 1, 60_000):
        record_route_snapshots(db, stamp, [{
            "symbol": symbol, "buy_venue": "deribit", "sell_venue": "rich",
            "gross_edge_bps": 100.0, "reference_mid_price": 101.0,
        }])
    books = {
        "deribit": _venue("deribit", 99.8, 99.9, timestamp=now),
        "rich": _venue("rich", 102.0, 102.1, timestamp=now),
    }
    # Without funding this would be accepted; funding cost must flip it to reject.
    monkeypatch.setattr(v20, "post_fill_entry_ev", lambda **kwargs: {
        "tradeable": True,
        "post_fill_expected_value_bps": 5.0,
        "minimum_required_ev_bps": 1.0,
    })

    v20._process_maker_probes_v20(
        state, books_by_symbol={symbol: books}, stats_db=db, now_ms=now,
        maker_fee_bps={"deribit": 1.5, "rich": 2.0},
        taker_fee_bps={"deribit": 3.5, "rich": 5.0},
        strict_maker_price_through=True,
    )
    calibration = v20_execution_calibration(db, venue="deribit", side="LONG")
    assert calibration["local_accept_count"] == 0
    assert calibration["local_reject_count"] == 1


def test_v20_discrete_funding_event_is_realized_once_if_position_crosses_settlement(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _accrue_v20_continuous_funding

    state = {
        "venue_balances": {"okx": 50.0, "other": 50.0},
        "equity": 100.0,
        "realized_pnl": 0.0,
        "realized_funding_pnl": 0.0,
        "funding_snapshots": {
            "okx|AAA/USDT:USDT": {
                # New upcoming period after the crossed event.
                "fundingRate": 0.0002,
                "fundingTimestamp": 2_000_000,
                "markPrice": 110.0,
                "sampled_at_ms": 1_060_000,
            }
        },
        "open_positions": [{
            "position_id": "p-discrete",
            "symbol": "AAA/USDT:USDT",
            "long_exchange": "okx",
            "short_exchange": "other",
            "quantity": 100.0,
            "opened_at_ms": 900_000,
            # Last causal quote for the funding event that settled at 1_050_000.
            "long_funding_rate": 0.0001,
            "long_funding_mark_price": 100.0,
            "long_funding_timestamp": 1_050_000,
        }],
    }
    journal = tmp_path / "funding.jsonl"
    _accrue_v20_continuous_funding(
        state, clients={}, now_ms=1_060_000,
        now_utc="2026-08-31T00:01:00+00:00", journal_path=journal,
    )
    assert state["realized_funding_pnl"] == pytest.approx(-1.0)
    assert state["equity"] == pytest.approx(99.0)
    event = __import__("json").loads(journal.read_text().strip())
    assert event["venue"] == "okx"
    assert event["funding_timestamp_ms"] == 1_050_000

    # Same crossed event cannot be charged twice.
    _accrue_v20_continuous_funding(
        state, clients={}, now_ms=1_070_000,
        now_utc="2026-08-31T00:01:10+00:00", journal_path=journal,
    )
    assert state["realized_funding_pnl"] == pytest.approx(-1.0)
    assert len(journal.read_text().strip().splitlines()) == 1


def test_v20_new_positions_pin_causal_funding_state_at_open():
    from scripts.run_arbitrage_paper_v20 import _seed_new_position_funding_state

    symbol = "AAA/USDC:USDC"
    state = {
        "funding_snapshots": {
            f"deribit|{symbol}": {
                "fundingRate": 0.0008, "markPrice": 100.0,
                "sampled_at_ms": 1_000_000,
            },
            f"okx|{symbol}": {
                "fundingRate": 0.0001, "markPrice": 101.0,
                "fundingTimestamp": 2_000_000, "sampled_at_ms": 1_000_000,
            },
        },
        "open_positions": [{
            "position_id": "new", "symbol": symbol,
            "long_exchange": "deribit", "short_exchange": "okx",
            "opened_at_ms": 1_000_000,
        }],
    }
    _seed_new_position_funding_state(state, previous_position_ids=set())
    position = state["open_positions"][0]
    assert position["long_funding_rate"] == pytest.approx(0.0008)
    assert position["long_funding_mark_price"] == pytest.approx(100.0)
    assert position["funding_last_accrual_ms"] == 1_000_000
    assert position["short_funding_rate"] == pytest.approx(0.0001)
    assert position["short_funding_mark_price"] == pytest.approx(101.0)
    assert position["short_funding_timestamp"] == 2_000_000


def test_v20_parser_defaults_to_fresh_math_calibration_without_legacy_seeds():
    from scripts.run_arbitrage_paper_v20 import _parser_v20

    args = _parser_v20().parse_args([])
    assert args.seed_history_db is None
    assert args.seed_execution_journal is None
    assert args.symbols == 50


def test_v20_funding_refresh_does_not_swallow_cancellation():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class CancelClient:
        has = {"fetchFundingRates": False}

        async def fetch_funding_rate(self, symbol):
            del symbol
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_refresh_funding_snapshots_v20(
            clients={"okx": CancelClient()}, state={}, symbols=["A/USDT:USDT"],
            coverage={"A/USDT:USDT": ("okx",)}, now_ms=1_000_000,
        ))


def test_v20_production_client_factory_excludes_deribit_until_latency_safe_mark_feed():
    from scripts.run_arbitrage_paper_v20 import make_public_stream_clients_v20

    clients = make_public_stream_clients_v20()
    assert "deribit" not in clients
    assert set(clients) == {"binance", "okx", "mexc", "bybit", "bitget", "kucoin", "gate"}


def test_v20_funding_refresh_enriches_active_position_mark_price():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class MarkClient:
        has = {"fetchFundingRates": False, "fetchMarkPrice": True}

        async def fetch_funding_rate(self, symbol):
            return {
                "symbol": symbol, "fundingRate": 0.0001,
                "fundingTimestamp": 2_000_000, "interval": "8h", "markPrice": None,
            }

        async def fetch_mark_price(self, symbol):
            return {"symbol": symbol, "last": 101.25, "info": {}}

    symbol = "A/USDT:USDT"
    state = {
        "open_positions": [{
            "position_id": "p", "symbol": symbol,
            "long_exchange": "okx", "short_exchange": "other", "quantity": 1.0,
        }]
    }
    asyncio.run(_refresh_funding_snapshots_v20(
        clients={"okx": MarkClient()}, state=state, symbols=[symbol],
        coverage={symbol: ("okx",)}, now_ms=1_000_000,
    ))
    assert state["funding_snapshots"][f"okx|{symbol}"]["markPrice"] == pytest.approx(101.25)


def test_v20_funding_refresh_reads_mexc_fair_price_as_mark_without_extra_call():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class MexcClient:
        has = {"fetchFundingRates": False, "fetchMarkPrice": None}

        async def fetch_funding_rate(self, symbol):
            return {
                "symbol": symbol, "fundingRate": 0.0001,
                "fundingTimestamp": 2_000_000, "interval": "8h", "markPrice": None,
                "info": {"fairPrice": "99.75"},
            }

    symbol = "A/USDT:USDT"
    state = {}
    asyncio.run(_refresh_funding_snapshots_v20(
        clients={"mexc": MexcClient()}, state=state, symbols=[symbol],
        coverage={symbol: ("mexc",)}, now_ms=1_000_000,
    ))
    assert state["funding_snapshots"][f"mexc|{symbol}"]["markPrice"] == pytest.approx(99.75)


def test_v20_active_mark_enrichment_runs_even_when_funding_snapshot_is_still_fresh():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class MarkClient:
        has = {"fetchFundingRates": False, "fetchMarkPrice": True}
        async def fetch_funding_rate(self, symbol):
            raise AssertionError("fresh funding snapshot should not refetch funding")
        async def fetch_mark_price(self, symbol):
            return {"symbol": symbol, "last": 102.5, "info": {}}

    symbol = "A/USDT:USDT"
    state = {
        "funding_snapshots": {
            f"okx|{symbol}": {
                "venue": "okx", "symbol": symbol, "fundingRate": 0.0001,
                "fundingTimestamp": 2_000_000, "markPrice": None,
                "sampled_at_ms": 999_000,
            }
        },
        "open_positions": [{
            "position_id": "p", "symbol": symbol, "long_exchange": "okx",
            "short_exchange": "other", "quantity": 1.0,
        }],
    }
    asyncio.run(_refresh_funding_snapshots_v20(
        clients={"okx": MarkClient()}, state=state, symbols=[symbol],
        coverage={symbol: ("okx",)}, now_ms=1_000_000,
    ))
    assert state["funding_snapshots"][f"okx|{symbol}"]["markPrice"] == pytest.approx(102.5)


def test_v20_discrete_position_pins_funding_schedule_even_if_mark_arrives_later():
    from scripts.run_arbitrage_paper_v20 import _seed_new_position_funding_state

    symbol = "A/USDT:USDT"
    state = {
        "funding_snapshots": {
            f"okx|{symbol}": {
                "fundingRate": 0.0001, "fundingTimestamp": 2_000_000,
                "markPrice": None, "sampled_at_ms": 1_000_000,
            }
        },
        "open_positions": [{
            "position_id": "p", "symbol": symbol, "long_exchange": "okx",
            "short_exchange": "other", "opened_at_ms": 1_000_000,
        }],
    }
    _seed_new_position_funding_state(state, previous_position_ids=set())
    position = state["open_positions"][0]
    assert position["long_funding_rate"] == pytest.approx(0.0001)
    assert position["long_funding_timestamp"] == 2_000_000
    assert "long_funding_mark_price" not in position


def test_v20_bulk_funding_missing_timestamp_falls_back_to_single_symbol():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class BulkClient:
        has = {"fetchFundingRates": True}

        def __init__(self):
            self.bulk_calls = 0
            self.single_calls = []

        async def fetch_funding_rates(self, symbols):
            self.bulk_calls += 1
            return {
                symbol: {
                    "symbol": symbol,
                    "fundingRate": 0.0001,
                    "fundingTimestamp": None,
                    "nextFundingTimestamp": None,
                }
                for symbol in symbols
            }

        async def fetch_funding_rate(self, symbol):
            self.single_calls.append(symbol)
            return {
                "symbol": symbol,
                "fundingRate": 0.0001,
                "fundingTimestamp": 9_000_000,
                "nextFundingTimestamp": 37_800_000,
                "interval": "8h",
            }

    client = BulkClient()
    state = {}
    symbol = "AAA/USDT:USDT"
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"bitget": client},
            state=state,
            symbols=[symbol],
            coverage={symbol: ("bitget",)},
            now_ms=1_000_000,
        )
    )

    assert client.bulk_calls == 1
    assert client.single_calls == [symbol]
    snapshot = state["funding_snapshots"][f"bitget|{symbol}"]
    assert snapshot["fundingTimestamp"] == 9_000_000
    assert state["funding_snapshot_error_count"] == 0


def test_v20_funding_refresh_is_global_clocked_across_discovery_batches():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class FundingClient:
        has = {"fetchFundingRates": True}

        def __init__(self):
            self.bulk_calls = []

        async def fetch_funding_rates(self, symbols):
            self.bulk_calls.append(tuple(symbols))
            return {
                symbol: {
                    "symbol": symbol,
                    "fundingRate": 0.0001,
                    "fundingTimestamp": 99_000_000,
                    "nextFundingTimestamp": 127_800_000,
                    "interval": "8h",
                }
                for symbol in symbols
            }

    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT"]
    client = FundingClient()
    state = {}
    coverage = {symbol: ("cheap",) for symbol in symbols}

    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"cheap": client},
            state=state,
            symbols=[symbols[0]],
            coverage=coverage,
            now_ms=1_000_000,
            refresh_interval_ms=60_000,
        )
    )
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"cheap": client},
            state=state,
            symbols=[symbols[1]],
            coverage=coverage,
            now_ms=1_001_000,
            refresh_interval_ms=60_000,
        )
    )

    assert client.bulk_calls == [tuple(symbols)]
    assert set(state["funding_snapshots"]) == {f"cheap|{symbol}" for symbol in symbols}
    assert state["funding_last_full_refresh_ms"] == 1_000_000


def test_v20_nonbatch_funding_refresh_is_scoped_to_current_symbols():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class FundingClient:
        has = {"fetchFundingRates": False}

        def __init__(self):
            self.calls = []

        async def fetch_funding_rate(self, symbol):
            self.calls.append(symbol)
            return {
                "symbol": symbol,
                "fundingRate": 0.0001,
                "fundingTimestamp": 99_000_000,
                "nextFundingTimestamp": 127_800_000,
                "interval": "8h",
            }

    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT", "CCC/USDT:USDT"]
    client = FundingClient()
    state = {}
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"mexc": client},
            state=state,
            symbols=[symbols[0]],
            coverage={symbol: ("mexc",) for symbol in symbols},
            now_ms=1_000_000,
        )
    )

    assert client.calls == [symbols[0]]
    assert set(state["funding_snapshots"]) == {f"mexc|{symbols[0]}"}


def test_v20_nonbatch_funding_refresh_includes_off_batch_active_position():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class FundingClient:
        has = {"fetchFundingRates": False}

        def __init__(self):
            self.calls = []

        async def fetch_funding_rate(self, symbol):
            self.calls.append(symbol)
            return {
                "symbol": symbol,
                "fundingRate": 0.0001,
                "fundingTimestamp": 99_000_000,
                "nextFundingTimestamp": 127_800_000,
                "interval": "8h",
            }

    current = "AAA/USDT:USDT"
    active = "BBB/USDT:USDT"
    client = FundingClient()
    state = {
        "open_positions": [{
            "symbol": active,
            "long_exchange": "mexc",
            "short_exchange": "other",
        }]
    }
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"mexc": client},
            state=state,
            symbols=[current],
            coverage={current: ("mexc",), active: ("mexc",)},
            now_ms=1_000_000,
        )
    )

    assert set(client.calls) == {current, active}
    assert set(state["funding_snapshots"]) == {f"mexc|{current}", f"mexc|{active}"}


def test_v20_nonbatch_funding_refresh_runs_symbols_concurrently():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class FundingClient:
        has = {"fetchFundingRates": False}

        def __init__(self):
            self.in_flight = 0
            self.max_in_flight = 0

        async def fetch_funding_rate(self, symbol):
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            await asyncio.sleep(0)
            self.in_flight -= 1
            return {
                "symbol": symbol,
                "fundingRate": 0.0001,
                "fundingTimestamp": 99_000_000,
                "nextFundingTimestamp": 127_800_000,
                "interval": "8h",
            }

    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT", "CCC/USDT:USDT"]
    client = FundingClient()
    state = {}
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"mexc": client},
            state=state,
            symbols=symbols,
            coverage={symbol: ("mexc",) for symbol in symbols},
            now_ms=1_000_000,
        )
    )

    assert client.max_in_flight >= 2
    assert len(state["funding_snapshots"]) == 3


def test_v20_funding_timestamp_fallbacks_run_concurrently():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class FundingClient:
        has = {"fetchFundingRates": True}

        def __init__(self):
            self.in_flight = 0
            self.max_in_flight = 0

        async def fetch_funding_rates(self, symbols):
            return {
                symbol: {
                    "symbol": symbol,
                    "fundingRate": 0.0001,
                    "fundingTimestamp": None,
                    "nextFundingTimestamp": None,
                    "interval": "8h",
                }
                for symbol in symbols
            }

        async def fetch_funding_rate(self, symbol):
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            await asyncio.sleep(0)
            self.in_flight -= 1
            return {
                "symbol": symbol,
                "fundingRate": 0.0001,
                "fundingTimestamp": 99_000_000,
                "nextFundingTimestamp": 127_800_000,
                "interval": "8h",
            }

    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT", "CCC/USDT:USDT"]
    client = FundingClient()
    state = {}
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"bitget": client},
            state=state,
            symbols=[symbols[0]],
            coverage={symbol: ("bitget",) for symbol in symbols},
            now_ms=1_000_000,
        )
    )

    assert set(state["funding_snapshots"]) == {f"bitget|{symbols[0]}"}

    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"bitget": client},
            state=state,
            symbols=symbols[1:],
            coverage={symbol: ("bitget",) for symbol in symbols},
            now_ms=1_001_000,
        )
    )

    assert client.max_in_flight >= 2
    assert set(state["funding_snapshots"]) == {f"bitget|{symbol}" for symbol in symbols}


def test_v20_funding_refresh_times_out_stalled_public_request():
    import asyncio

    from scripts.run_arbitrage_paper_v20 import _refresh_funding_snapshots_v20

    class HungBatchClient:
        has = {"fetchFundingRates": True}

        async def fetch_funding_rates(self, symbols):
            del symbols
            await asyncio.Event().wait()

        async def fetch_funding_rate(self, symbol):
            del symbol
            await asyncio.Event().wait()

    state = {}
    asyncio.run(
        _refresh_funding_snapshots_v20(
            clients={"binance": HungBatchClient()},
            state=state,
            symbols=["AAA/USDT:USDT"],
            coverage={"AAA/USDT:USDT": ("binance",)},
            now_ms=1_000_000,
            request_timeout_seconds=0.01,
        )
    )

    assert state["funding_full_refresh_count"] == 1
    assert state["funding_snapshot_count"] == 0
    assert state["funding_snapshot_error_count"] >= 1


def test_shared_runner_honors_shadow_probe_quality_metadata(tmp_path, monkeypatch):
    from scripts import run_arbitrage_paper_v17 as v17

    class Client:
        def __init__(self, book):
            self.book = book
        def fetch_order_book(self, symbol, limit=None):
            del symbol, limit
            return self.book

    symbol = "PROBE/USDT:USDT"
    now = 7_000_000
    clients = {
        "cheap": Client({"bids": [[99.9, 100.0]], "asks": [[100.0, 100.0]], "timestamp": now}),
        "rich": Client({"bids": [[102.0, 100.0]], "asks": [[102.1, 100.0]], "timestamp": now}),
    }
    monkeypatch.setattr(
        v17,
        "multi_horizon_route_features",
        lambda *args, **kwargs: {
            "baseline_60m_bps": 1.0,
            "baseline_15m_bps": 1.0,
            "baseline_5m_bps": 1.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 3.0,
        },
    )

    def route_decider(opportunity, **kwargs):
        del kwargs
        allowed = opportunity.buy_venue == "cheap"
        return {
            "tradeable": False,
            "decision": "WATCH",
            "expected_value_bps": -1.0,
            "minimum_required_ev_bps": 0.5,
            "capture_bps": 20.0 if allowed else 30.0,
            "conditional_pair_value_bps": 8.0 if allowed else -2.0,
            "shadow_probe_eligible": allowed,
            "shadow_probe_priority": 8.0 if allowed else 100.0,
            "z_score": 2.0,
            "baseline_60m_bps": 1.0,
            "baseline_15m_bps": 1.0,
            "baseline_5m_bps": 1.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 3.0,
            "p_open": 0.2,
        }

    state = v17._default_state_v17(list(clients))
    v17.run_cycle_v17(
        clients=clients,
        symbols=[symbol],
        state=state,
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.0},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=now,
        now_utc="2026-08-31T06:30:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={symbol: ("cheap", "rich")},
        route_decider=route_decider,
        max_pending_entries=0,
        max_probes=1,
    )

    assert len(state["maker_probes"]) == 1
    probe = state["maker_probes"][0]
    assert probe["long_exchange"] == "cheap"
    assert probe["placement_capture_bps"] == pytest.approx(20.0)
    assert probe["placement_pair_value_bps"] == pytest.approx(8.0)


def test_shared_runner_can_make_risk_exit_immediate(tmp_path, monkeypatch):
    from scripts import run_arbitrage_paper_v17 as v17

    class Client:
        def __init__(self, book):
            self.book = book
        def fetch_order_book(self, symbol, limit=None):
            del symbol, limit
            return self.book

    symbol = "EXIT/USDT:USDT"
    now = 1_000_000
    venues, pending = _pending("LONG", now_ms=now)
    state = _state()
    state["pending_entries"] = [pending]
    # Causally fill the long maker and open a paired position first.
    opening = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=now + 5_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=now + 5_000),
    }
    from scripts.run_arbitrage_paper_v19 import _process_pending_entries_v19
    _process_pending_entries_v19(
        state,
        books_by_symbol={"AAA/USDT:USDT": opening},
        stats_db=tmp_path / "stats.sqlite",
        now_ms=now + 5_000,
        now_utc="2026-08-31T06:30:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
    )
    assert len(state["open_positions"]) == 1
    position = state["open_positions"][0]
    symbol = position["symbol"]
    close_clients = {
        "cheap": Client({"bids": [[99.6, 100.0]], "asks": [[99.7, 100.0]], "timestamp": now + 10_000}),
        "rich": Client({"bids": [[106.1, 100.0]], "asks": [[106.2, 100.0]], "timestamp": now + 10_000}),
    }
    monkeypatch.setattr(v17, "multi_horizon_route_features", lambda *args, **kwargs: None)

    v17.run_cycle_v17(
        clients=close_clients,
        symbols=[symbol],
        state=state,
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=now + 10_000,
        now_utc="2026-08-31T06:30:10+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={symbol: ("cheap", "rich")},
        max_pending_entries=0,
        max_probes=0,
        exit_decider=lambda *args, **kwargs: "DIVERGENCE_STOP",
        immediate_exit_reasons={"DIVERGENCE_STOP"},
    )

    assert state["open_positions"] == []
    assert state["pending_exits"] == []
    assert state["last_close"]["close_reason"] == "DIVERGENCE_STOP"


def test_v20_pending_processor_can_delegate_terminal_calibration_recording(tmp_path):
    from scripts.run_arbitrage_paper_v20 import _process_pending_entries_v20

    _, pending = _pending("LONG")
    state = _state()
    state["pending_entries"] = [pending]
    calls = []
    books = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=1_005_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=1_005_000),
    }
    _process_pending_entries_v20(
        state,
        books_by_symbol={"AAA/USDT:USDT": books},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_005_000,
        now_utc="2026-08-31T06:40:05+00:00",
        journal_path=tmp_path / "positions.jsonl",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
        terminal_outcome_recorder=lambda row, **kwargs: calls.append((row, kwargs)),
    )

    assert len(calls) == 1
    assert calls[0][1]["accepted"] is True
    # A delegated recorder owns calibration; V20's aggregate must stay untouched.
    calibration = v20_execution_calibration(tmp_path / "history.sqlite", venue="cheap", side="LONG")
    assert calibration["local_fill_count"] == 0


def test_v20_shadow_processor_can_delegate_auditable_outcome_recording(tmp_path):
    from scripts.run_arbitrage_paper_v17 import _probe_from_route
    from scripts.run_arbitrage_paper_v20 import _process_maker_probes_v20

    symbol = "SHADOWHOOK/USDT:USDT"
    placed_ms = 2_000_000
    venues = {
        "cheap": _venue("cheap", 99.9, 100.0, timestamp=placed_ms),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms),
    }
    opportunity = evaluate_pair(
        symbol, venues["cheap"], venues["rich"],
        target_notional=10.0, safety_buffer_bps=0.5, allow_nonpositive=True,
    )
    assert opportunity is not None
    probe = _probe_from_route(
        opportunity,
        venues,
        now_ms=placed_ms,
        decision={"capture_bps": 25.0, "conditional_pair_value_bps": 12.0},
    )
    state = _state()
    state["maker_probes"] = [probe]
    state["funding_snapshots"] = {
        f"cheap|{symbol}": {**_funding_snapshot(0.0, funding_ts=placed_ms + 8 * 60 * 60_000), "sampled_at_ms": placed_ms + 5_000},
        f"rich|{symbol}": {**_funding_snapshot(0.0, funding_ts=placed_ms + 8 * 60 * 60_000), "sampled_at_ms": placed_ms + 5_000},
    }
    db = tmp_path / "history.sqlite"
    _seed_route_history(db, symbol=symbol, buy_venue="cheap", sell_venue="rich", now_ms=placed_ms + 5_000)
    later = {
        "cheap": _venue("cheap", 99.7, 99.8, timestamp=placed_ms + 5_000),
        "rich": _venue("rich", 106.0, 106.1, fee=5.5, timestamp=placed_ms + 5_000),
    }
    calls = []
    _process_maker_probes_v20(
        state,
        books_by_symbol={symbol: later},
        stats_db=db,
        now_ms=placed_ms + 5_000,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        strict_maker_price_through=True,
        shadow_outcome_recorder=lambda row, **kwargs: calls.append((row, kwargs)),
        counter_prefix="v21",
    )

    assert len(calls) == 1
    assert calls[0][0]["placement_capture_bps"] == pytest.approx(25.0)
    assert calls[0][1]["side"] == "LONG"
    assert calls[0][1]["accepted"] is True
    assert calls[0][1]["post_fill_ev_bps"] > 0.0
    assert state["v21_shadow_accept_count"] == 1

@pytest.mark.asyncio
async def test_v21_isolates_background_funding_from_websocket_event_loop(monkeypatch):
    from types import SimpleNamespace
    from scripts import run_arbitrage_paper_v19 as v19
    from scripts import run_arbitrage_paper_v20 as v20
    from scripts import run_arbitrage_paper_v21 as v21

    captured = {}

    async def fake_run(args, **kwargs):
        del args
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(v19, "_run", fake_run)
    result = await v21._run_v21(SimpleNamespace())

    assert result == 0
    assert captured["runtime_refresher_threaded"] is True
    assert captured["runtime_clients_factory"] is v20.make_public_funding_clients_v20
