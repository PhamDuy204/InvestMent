import pytest

from crypto_research.arbitrage_v12 import VenueBook, evaluate_pair
from crypto_research.maker_v21 import record_v21_execution_outcome


def _venue(name, bid, ask, *, fee=5.0, timestamp=1_000_000):
    return VenueBook(
        name,
        {
            "bids": [[bid, 100.0]],
            "asks": [[ask, 100.0]],
            "timestamp": timestamp,
            "received_at_ms": timestamp,
        },
        fee,
    )


def _funding(symbol, now):
    return {
        f"cheap|{symbol}": {
            "fundingRate": 0.0,
            "fundingTimestamp": now + 8 * 60 * 60_000,
            "sampled_at_ms": now,
        },
        f"rich|{symbol}": {
            "fundingRate": 0.0,
            "fundingTimestamp": now + 8 * 60 * 60_000,
            "sampled_at_ms": now,
        },
    }


def _opportunity():
    symbol = "V21/USDT:USDT"
    venues = {
        "cheap": _venue("cheap", 99.8, 100.0),
        "rich": _venue("rich", 102.0, 102.2, fee=5.5),
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
    return symbol, venues, opportunity


def _features():
    return {
        "baseline_60m_bps": 160.0,
        "baseline_15m_bps": 160.0,
        "baseline_5m_bps": 160.0,
        "route_sigma_bps": 2.0,
        "price_volatility_bps": 4.0,
    }


def test_v21_positive_after_cost_route_is_shadow_eligible_during_cohort_warmup(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v20 as v20
    from scripts.run_arbitrage_paper_v21 import _v21_route_decision

    monkeypatch.setattr(
        v20,
        "conservative_fill_probability",
        lambda *args, **kwargs: {"conservative_probability": 0.5, "attempts": 100, "fills": 50},
    )
    symbol, venues, opportunity = _opportunity()
    now = 1_000_000
    decision = _v21_route_decision(
        opportunity,
        features=_features(),
        stats_db=tmp_path / "history.sqlite",
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots=_funding(symbol, now),
        now_ms=now,
    )

    assert decision["tradeable"] is False
    assert decision["shadow_probe_eligible"] is True
    assert decision["shadow_probe_priority"] > 0.0
    assert decision["decision"] == "V21_EXECUTION_CALIBRATION_WARMUP"


def test_v21_route_can_enter_when_90pct_confidence_bound_keeps_ev_positive(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v20 as v20
    from scripts.run_arbitrage_paper_v21 import _v21_route_decision

    monkeypatch.setattr(
        v20,
        "conservative_fill_probability",
        lambda *args, **kwargs: {"conservative_probability": 0.5, "attempts": 100, "fills": 50},
    )
    db = tmp_path / "history.sqlite"
    symbol, venues, opportunity = _opportunity()
    now = 1_000_000
    warmup = _v21_route_decision(
        opportunity,
        features=_features(),
        stats_db=db,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots=_funding(symbol, now),
        now_ms=now,
    )
    capture = float(warmup["capture_bps"])
    for venue, side in (("cheap", "LONG"), ("rich", "SHORT")):
        for _ in range(9):
            record_v21_execution_outcome(
                db,
                venue=venue,
                side=side,
                placement_capture_bps=capture,
                post_fill_ev_bps=8.0,
                accepted=True,
            )
        record_v21_execution_outcome(
            db,
            venue=venue,
            side=side,
            placement_capture_bps=capture,
            post_fill_ev_bps=-2.0,
            accepted=False,
            reject_net_bps=-10.0,
        )

    decision = _v21_route_decision(
        opportunity,
        features=_features(),
        stats_db=db,
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        safety_buffer_bps=0.5,
        venues=venues,
        funding_snapshots=_funding(symbol, now),
        now_ms=now,
    )

    assert decision["estimated_accept_probability"] == pytest.approx(0.90)
    assert decision["post_fill_accept_probability"] < 0.90
    assert decision["expected_attempt_ev_bps"] > decision["minimum_required_ev_bps"]
    assert decision["tradeable"] is True
    assert decision["decision"] == "V21_RISK_ADJUSTED_EV_ACCEPTED"


def test_v21_state_describes_90pct_as_confidence_bound_not_hard_accept_rate():
    from scripts.run_arbitrage_paper_v21 import _default_state_v21

    state = _default_state_v21(["cheap", "rich"])
    assert state["execution_acceptance_policy"] == (
        "COHORT_90PCT_CONFIDENCE_BOUND_AND_POSITIVE_CONSERVATIVE_EV"
    )


def test_v21_restart_discards_inflight_shadow_probes_without_recording_outcomes(tmp_path):
    import sqlite3

    from scripts.run_arbitrage_paper_v21 import (
        _default_state_v21,
        _initialize_v21_runtime,
    )

    state = _default_state_v21(["cheap", "rich"])
    state["maker_probes"] = [{"probe_id": "interrupted"}]
    history_db = tmp_path / "history.sqlite"

    _initialize_v21_runtime(
        state=state,
        history_db=history_db,
        artifacts=tmp_path,
        args=object(),
        symbols=["V21/USDT:USDT"],
        coverage={"V21/USDT:USDT": ("cheap", "rich")},
    )

    assert state["maker_probes"] == []
    assert state["maker_probe_restart_discard_count"] == 1
    with sqlite3.connect(history_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM maker_execution_events_v21"
        ).fetchone()[0] == 0


def test_v21_divergence_exit_requires_two_confirmations():
    from scripts.run_arbitrage_paper_v21 import _confirm_v21_exit

    state = {}
    position = {"position_id": "p1"}
    assert _confirm_v21_exit(state, position, "DIVERGENCE_STOP", now_ms=1_000) is None
    assert _confirm_v21_exit(state, position, "DIVERGENCE_STOP", now_ms=1_600) == "DIVERGENCE_STOP"


def test_v21_shadow_and_pending_recorders_preserve_capture_cohort(tmp_path):
    from crypto_research.maker_v21 import v21_execution_calibration
    from scripts.run_arbitrage_paper_v21 import (
        _record_v21_pending_outcome,
        _record_v21_shadow_outcome,
    )

    db = tmp_path / "history.sqlite"
    probe = {"placement_capture_bps": 24.0}
    _record_v21_shadow_outcome(
        db,
        2_000_000,
        probe,
        venue="gate",
        side="LONG",
        accepted=True,
        post_fill_ev_bps=5.0,
        reject_net_bps=None,
    )
    pending = {
        "maker_side": "LONG",
        "long_exchange": "gate",
        "short_exchange": "rich",
        "capture_bps": 24.0,
        "post_fill_expected_value_bps": -3.0,
        "long_limit_price": 100.0,
        "short_limit_price": 101.0,
        "quantity": 0.1,
    }
    _record_v21_pending_outcome(
        db,
        2_001_000,
        {},
        pending,
        accepted=False,
        realized_net_pnl=-0.01,
    )
    calibration = v21_execution_calibration(
        db, venue="gate", side="LONG", placement_capture_bps=24.0
    )
    assert calibration["local_fill_count"] == 2
    assert calibration["local_accept_count"] == 1
    assert calibration["local_reject_count"] == 1


def test_v21_route_limits_sample_eight_but_admit_six(tmp_path, monkeypatch):
    from crypto_research.arbitrage_v12 import ArbitrageOpportunity
    from scripts.run_arbitrage_paper_v17 import _default_state_v17, run_cycle_v17
    import scripts.run_arbitrage_paper_v17 as v17

    class FakeClient:
        def __init__(self, books):
            self.books = books

        def fetch_order_book(self, symbol, limit=None):
            return self.books[symbol]

        def create_order(self, *args, **kwargs):  # pragma: no cover - safety trap
            raise AssertionError("private order path must never be called")

    symbol = "ROUTES/USDT:USDT"
    now_ms = 8_000_000
    raw_cheap = {"bids": [[99.9, 100.0]], "asks": [[100.0, 100.0]], "timestamp": now_ms}
    raw_rich = {"bids": [[102.0, 100.0]], "asks": [[102.1, 100.0]], "timestamp": now_ms}
    clients = {
        "cheap": FakeClient({symbol: raw_cheap}),
        "rich": FakeClient({symbol: raw_rich}),
    }
    routes = [
        ArbitrageOpportunity(
            symbol=symbol,
            buy_venue="cheap",
            sell_venue="rich",
            target_notional=10.0,
            buy_vwap=100.0,
            sell_vwap=102.0 + i * 0.01,
            gross_edge_bps=200.0 + i,
            total_fee_bps=10.5,
            safety_buffer_bps=0.5,
            net_edge_bps=189.0 + i,
        )
        for i in range(8)
    ]
    monkeypatch.setattr(v17, "_all_routes", lambda *args, **kwargs: routes)
    recorded = []
    monkeypatch.setattr(
        v17,
        "record_route_snapshots",
        lambda db, sampled_at_ms, rows: recorded.extend(rows) or len(rows),
    )
    decisions = []

    def route_decider(opportunity, **kwargs):
        decisions.append(opportunity)
        return {
            "tradeable": False,
            "decision": "NO_ROUTE_DISLOCATION",
            "expected_value_bps": -1.0,
        }

    state = _default_state_v17(list(clients))
    run_cycle_v17(
        clients=clients,
        symbols=[symbol],
        state=state,
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=now_ms,
        now_utc="2026-09-01T12:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={symbol: ("cheap", "rich")},
        route_decider=route_decider,
        route_history_limit=8,
        route_admission_limit=6,
    )

    assert len(recorded) == 8
    assert len(decisions) == 6
    assert len(state["opportunity_radar"]) == 6


def test_v21_uses_two_short_window_samples_to_match_scan_cadence(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v17 as v17
    import scripts.run_arbitrage_paper_v21 as v21

    captured = {}
    monkeypatch.setattr(v17, "run_cycle_v17", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(
        v21.v20,
        "_ensure_v20_runtime_imports",
        lambda: ({"okx": 5.0, "bybit": 5.5}, {"okx": 2.0, "bybit": 2.0}),
    )
    monkeypatch.setattr(v21.v20, "_accrue_v20_continuous_funding", lambda *args, **kwargs: None)

    state = v21._default_state_v21(["okx", "bybit"])
    v21.run_cycle_v21(
        clients={},
        symbols=[],
        state=state,
        history_db=tmp_path / "history.sqlite",
        now_ms=1_000_000,
        now_utc="2026-09-01T13:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={},
    )

    assert captured["minimum_window_samples"] == 2


def test_v21_uses_eight_history_samples_and_fast_window_is_diagnostic(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v17 as v17
    import scripts.run_arbitrage_paper_v21 as v21

    captured = {}
    monkeypatch.setattr(v17, "run_cycle_v17", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(
        v21.v20,
        "_ensure_v20_runtime_imports",
        lambda: ({"okx": 5.0, "bybit": 5.5}, {"okx": 2.0, "bybit": 2.0}),
    )
    monkeypatch.setattr(v21.v20, "_accrue_v20_continuous_funding", lambda *args, **kwargs: None)

    v21.run_cycle_v21(
        clients={},
        symbols=[],
        state=v21._default_state_v21(["okx", "bybit"]),
        history_db=tmp_path / "history.sqlite",
        now_ms=1_000_000,
        now_utc="2026-09-01T14:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={},
    )

    assert captured["minimum_history_samples"] == 8
    assert captured["require_5m_window"] is False


def test_v21_shadow_processor_uses_same_history_policy(tmp_path, monkeypatch):
    import scripts.run_arbitrage_paper_v21 as v21

    captured = {}
    monkeypatch.setattr(
        v21.v20,
        "_process_maker_probes_v20",
        lambda *args, **kwargs: captured.update(kwargs),
    )
    v21._process_maker_probes_v21(
        {},
        books_by_symbol={},
        stats_db=tmp_path / "history.sqlite",
        now_ms=1_000_000,
        maker_fee_bps={},
        taker_fee_bps={},
    )

    assert captured["feature_min_samples"] == 8
    assert captured["feature_minimum_window_samples"] == 2
    assert captured["feature_require_5m_window"] is False
    assert captured["funding_max_hold_seconds"] == 35.0 * 60.0
    assert captured["price_discrete_funding"] is True


def test_v21_history_policy_reaches_reprice_feature_calls(tmp_path, monkeypatch):
    from scripts.run_arbitrage_paper_v17 import _default_state_v17, run_cycle_v17
    import scripts.run_arbitrage_paper_v17 as v17

    class FakeClient:
        def __init__(self, book):
            self.book = book

        def fetch_order_book(self, symbol, limit=None):
            return self.book

    symbol = "POLICY/USDT:USDT"
    now_ms = 9_000_000
    clients = {
        "cheap": FakeClient({"bids": [[99.9, 100.0]], "asks": [[100.0, 100.0]], "timestamp": now_ms}),
        "rich": FakeClient({"bids": [[102.0, 100.0]], "asks": [[102.1, 100.0]], "timestamp": now_ms}),
    }
    feature_calls = []

    def fake_features(*args, **kwargs):
        feature_calls.append(kwargs)
        return {
            "baseline_60m_bps": 1.0,
            "baseline_15m_bps": 1.0,
            "baseline_5m_bps": 1.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 3.0,
        }

    monkeypatch.setattr(v17, "multi_horizon_route_features", fake_features)

    def route_decider(opportunity, **kwargs):
        return {
            "tradeable": True,
            "decision": "POLICY_ACCEPT",
            "expected_value_bps": 5.0,
            "minimum_required_ev_bps": 0.5,
            "capture_bps": 20.0,
            "z_score": 3.0,
            "baseline_60m_bps": 1.0,
            "baseline_15m_bps": 1.0,
            "baseline_5m_bps": 1.0,
            "route_sigma_bps": 2.0,
            "price_volatility_bps": 3.0,
            "p_open": 0.5,
        }

    run_cycle_v17(
        clients=clients,
        symbols=[symbol],
        state=_default_state_v17(list(clients)),
        history_db=tmp_path / "history.sqlite",
        stats_db=tmp_path / "stats.sqlite",
        safety_buffer_bps=0.5,
        depth_limit=20,
        taker_fee_bps={"cheap": 5.0, "rich": 5.5},
        maker_fee_bps={"cheap": 2.0, "rich": 2.0},
        max_book_age_ms=10_000,
        now_ms=now_ms,
        now_utc="2026-09-01T15:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        symbol_venues={symbol: ("cheap", "rich")},
        route_decider=route_decider,
        minimum_history_samples=8,
        minimum_window_samples=2,
        require_5m_window=False,
    )

    assert len(feature_calls) >= 2
    assert all(call["min_samples"] == 8 for call in feature_calls)
    assert all(call["minimum_window_samples"] == 2 for call in feature_calls)
    assert all(call["require_5m_window"] is False for call in feature_calls)


def test_v21_allows_event_driven_books_to_idle_without_changing_v19_default():
    import scripts.run_arbitrage_paper_v19 as v19
    import scripts.run_arbitrage_paper_v21 as v21

    assert v19._parser().parse_args([]).max_book_age_ms == 5_000
    assert v21._parser_v21().parse_args([]).max_book_age_ms == 60_000


@pytest.mark.asyncio
async def test_v21_public_activity_uses_maker_venue_tickers_and_open_price_fallback():
    import scripts.run_arbitrage_paper_v21 as v21

    coverage = {
        "AAA/USDT:USDT": ("gate", "okx", "other"),
        "BBB/USDT:USDT": ("gate", "okx"),
        "IGNORED/USDT:USDT": ("okx", "other"),
    }

    class Exchange:
        has = {"fetchTickers": True}

        def __init__(self, tickers):
            self.tickers = tickers

        async def fetch_tickers(self):
            return self.tickers

    clients = {
        "okx": Exchange(
            {
                "AAA/USDT:USDT": {"percentage": -2.0},
                "BBB/USDT:USDT": {"last": 105.0, "open": 100.0},
                "NOT_COVERED/USDT:USDT": {"percentage": 99.0},
            }
        ),
        "gate": Exchange(
            {
                "AAA/USDT:USDT": {"percentage": 8.0},
                "BBB/USDT:USDT": {"percentage": 4.0},
            }
        ),
    }

    scores = await v21._load_v21_universe_activity(
        clients,
        coverage,
        timeout_seconds=0.1,
    )
    assert scores == pytest.approx(
        {
            "AAA/USDT:USDT": 8.0,
            "BBB/USDT:USDT": 5.0,
        }
    )


@pytest.mark.asyncio
async def test_v21_runs_funding_refresh_off_execution_path(monkeypatch):
    import scripts.run_arbitrage_paper_v19 as v19
    import scripts.run_arbitrage_paper_v21 as v21

    captured = {}

    async def fake_run_shared(args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(v19, "_run", fake_run_shared)
    args = v21._parser_v21().parse_args([])
    assert await v21._run_v21(args) == 0
    assert captured["runtime_refresher_background"] is True
    assert captured["public_trade_venues"] == ("okx", "gate")
    assert captured["universe_activity_loader"] is v21._load_v21_universe_activity
    assert set(captured["runtime_refresher_merge_keys"]) == {
        "funding_snapshots",
        "funding_snapshot_error_count",
        "funding_last_full_refresh_ms",
        "funding_full_refresh_count",
        "funding_snapshot_count",
    }


def test_v21_cycle_calibration_cache_reuses_matching_cohort(monkeypatch, tmp_path):
    import scripts.run_arbitrage_paper_v21 as v21

    calls = []

    def fake_provider(db_path, *, venue, side, placement_capture_bps):
        calls.append((str(db_path), venue, side, placement_capture_bps))
        return {"capture": placement_capture_bps}

    monkeypatch.setattr(v21, "_v21_calibration_provider", fake_provider)
    cache = {}
    first = v21._cycle_v21_calibration_provider(
        cache, tmp_path / "history.sqlite", venue="OKX", side="LONG", placement_capture_bps=41.0
    )
    second = v21._cycle_v21_calibration_provider(
        cache, tmp_path / "history.sqlite", venue="okx", side="long", placement_capture_bps=85.0
    )
    third = v21._cycle_v21_calibration_provider(
        cache, tmp_path / "history.sqlite", venue="okx", side="LONG", placement_capture_bps=35.0
    )

    assert first is second
    assert third is not first
    assert len(calls) == 2


def test_v21_route_decision_prices_discrete_funding(monkeypatch, tmp_path):
    import scripts.run_arbitrage_paper_v21 as v21
    from crypto_research.arbitrage_v12 import ArbitrageOpportunity

    captured = {}
    def fake_v20_decision(*args, **kwargs):
        captured.update(kwargs)
        return {
            "max_conditional_pair_value_bps": 0.0,
            "capture_bps": 0.0,
            "funding_ready": True,
            "tradeable": False,
            "decision": "TEST",
        }
    monkeypatch.setattr(v21.v20, "_v20_route_decision", fake_v20_decision)
    opportunity = ArbitrageOpportunity(
        symbol="AAA/USDT:USDT",
        buy_venue="binance",
        sell_venue="okx",
        target_notional=10.0,
        buy_vwap=100.0,
        sell_vwap=101.0,
        gross_edge_bps=99.5,
        total_fee_bps=20.0,
        safety_buffer_bps=0.5,
        net_edge_bps=79.0,
    )
    v21._v21_route_decision(
        opportunity,
        features={},
        stats_db=tmp_path / "history.sqlite",
        maker_fee_bps={"binance": 2.0, "okx": 2.0},
        taker_fee_bps={"binance": 5.0, "okx": 5.0},
        safety_buffer_bps=0.5,
        venues={},
        funding_snapshots={},
        now_ms=1_000_000,
    )
    assert captured["max_hold_seconds"] == 35.0 * 60.0
    assert captured["price_discrete_funding"] is True
