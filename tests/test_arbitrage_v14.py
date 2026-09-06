from __future__ import annotations

import pytest

from scripts.run_arbitrage_paper_v14 import (
    _default_state,
    _optimizer_score_bps,
    _parser,
    _refresh_cross_margin_summary,
    _sorted_universe,
    _upgrade_v14b_state_to_c,
    migrate_v13_state,
    run_cycle,
)


class FakePublicClient:
    def __init__(self, books):
        self.books = books
        self.public_calls = []

    def fetch_order_book(self, symbol, limit=None):
        self.public_calls.append(("fetch_order_book", symbol, limit))
        value = self.books[symbol]
        if isinstance(value, list):
            if not value:
                raise AssertionError(f"no more books for {symbol}")
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def create_order(self, *args, **kwargs):  # pragma: no cover - safety boundary
        raise AssertionError("private order path must never be called")


def _book(bid, ask, *, timestamp=1_000_000, qty=100.0):
    return {"bids": [[bid, qty]], "asks": [[ask, qty]], "timestamp": timestamp}


def _run(tmp_path, *, clients, symbols, state, now_ms=1_000_000, now_utc="2026-08-27T12:00:00+00:00", min_edge=5.0, max_hold=3600.0):
    run_cycle(
        clients=clients,
        symbols=symbols,
        state=state,
        min_net_edge_bps=min_edge,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=max_hold,
        depth_limit=20,
        fee_bps={name: 1.0 for name in clients},
        max_book_age_ms=10_000,
        now_ms=now_ms,
        now_utc=now_utc,
        journal_path=tmp_path / "positions.jsonl",
    )



def test_sorted_universe_spends_fixed_slots_on_distinct_bases_before_quote_variants():
    coverage = {
        "BTC/USDT:USDT": ("a", "b", "c", "d", "e", "f"),
        "BTC/USDC:USDC": ("a", "b"),
        "ETH/USDT:USDT": ("a", "b", "c", "d", "e"),
        "ETH/USDC:USDC": ("a", "b"),
        "FIL/USDT:USDT": ("a", "b", "c", "d"),
        "TIA/USDT:USDT": ("a", "b", "c"),
    }

    assert _sorted_universe(coverage, 4) == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "FIL/USDT:USDT",
        "TIA/USDT:USDT",
    ]


def test_sorted_universe_uses_public_activity_only_to_break_equal_coverage_ties():
    coverage = {
        "AAA/USDT:USDT": ("a", "b", "c"),
        "MID/USDT:USDT": ("a", "b", "c"),
        "ZZZ/USDT:USDT": ("a", "b", "c"),
    }

    assert _sorted_universe(
        coverage,
        2,
        activity_scores={
            "AAA/USDT:USDT": 1.0,
            "MID/USDT:USDT": 5.0,
            "ZZZ/USDT:USDT": 9.0,
        },
    ) == ["ZZZ/USDT:USDT", "MID/USDT:USDT"]


def test_default_state_uses_per_venue_cross_margin_collateral():
    state = _default_state(20.0, ["okx", "mexc"])

    assert state["schema_version"] == "v14-arbitrage-paper-1"
    assert state["margin_model"] == "CROSS_MARGIN_PAPER_V1"
    assert state["portfolio_model"] == "CROSS_MARGIN_OPTIMIZER_V1"
    assert state["maintenance_stress_rate"] == 0.05
    assert state["margin_utilization_cap"] == 0.8
    assert state["exchange_leverage"] == 2.0
    assert state["gross_leverage_cap"] == 2.0
    assert state["max_open_positions"] == 6
    assert state["single_pair_gross_fraction"] == 0.3
    assert state["venue_balances"] == {"mexc": 10.0, "okx": 10.0}


def test_cycle_ranks_candidates_by_net_edge_before_opening(tmp_path):
    weak = "AAA/USDT:USDT"
    strong = "BBB/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({weak: _book(99.9, 100.0), strong: _book(99.9, 100.0)}),
        "rich": FakePublicClient({weak: _book(100.4, 100.5), strong: _book(102.0, 102.1)}),
    }
    state = _default_state(20.0, clients, max_open_positions=1)

    _run(tmp_path, clients=clients, symbols=[weak, strong], state=state)

    assert [position["symbol"] for position in state["open_positions"]] == [strong]
    assert state["opportunity_radar"][0]["symbol"] == strong
    assert state["opportunity_radar"][0]["decision"] == "OPENED"


def test_cycle_opens_at_most_six_distinct_symbols_and_respects_gross_cap(tmp_path):
    symbols = [f"S{i}/USDT:USDT" for i in range(7)]
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0) for symbol in symbols}),
        "rich": FakePublicClient({symbol: _book(102.0 + i * 0.1, 102.1 + i * 0.1) for i, symbol in enumerate(symbols)}),
    }
    state = _default_state(20.0, clients)

    _run(tmp_path, clients=clients, symbols=symbols, state=state)

    assert 1 <= len(state["open_positions"]) <= 6
    assert len({position["symbol"] for position in state["open_positions"]}) == len(state["open_positions"])
    assert state["gross_exposure"] <= 40.1
    assert state["gross_leverage_used"] <= 2.0 + 1e-9
    assert any(row["decision"] in {"MAX_POSITIONS", "VENUE_MARGIN"} for row in state["opportunity_radar"])


def test_cycle_rejects_candidate_when_venue_margin_is_insufficient(tmp_path):
    symbol = "BTC/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0)}),
        "rich": FakePublicClient({symbol: _book(102.0, 102.1)}),
    }
    state = _default_state(20.0, clients)
    state["venue_balances"] = {"cheap": 1.0, "rich": 19.0}

    _run(tmp_path, clients=clients, symbols=[symbol], state=state)

    assert state["open_positions"] == []
    assert state["opportunity_radar"][0]["decision"] == "VENUE_MARGIN"


def test_cycle_rechecks_venue_margin_after_each_open(tmp_path):
    symbols = ["AAA/USDT:USDT", "BBB/USDT:USDT"]
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0) for symbol in symbols}),
        "rich": FakePublicClient({symbol: _book(102.0, 102.1) for symbol in symbols}),
    }
    state = _default_state(20.0, clients, single_pair_gross_fraction=0.1)
    state["venue_balances"] = {"cheap": 0.7, "rich": 19.3}

    _run(tmp_path, clients=clients, symbols=symbols, state=state)

    assert len(state["open_positions"]) == 1
    assert state["invariant_failure_count"] == 0
    assert any(row["decision"] == "VENUE_MARGIN" for row in state["opportunity_radar"])


def test_open_position_records_modeled_initial_margin(tmp_path):
    symbol = "BTC/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0)}),
        "rich": FakePublicClient({symbol: _book(102.0, 102.1)}),
    }
    state = _default_state(20.0, clients)

    _run(tmp_path, clients=clients, symbols=[symbol], state=state)

    position = state["open_positions"][0]
    assert position["margin_model"] == "CROSS_MARGIN_PAPER_V1"
    assert position["leverage"] == 2.0
    assert position["long_initial_margin"] == pytest.approx(position["long_entry_notional"] / 2.0)
    assert position["short_initial_margin"] == pytest.approx(position["short_entry_notional"] / 2.0)
    assert position["initial_margin"] == pytest.approx(
        position["long_initial_margin"] + position["short_initial_margin"]
    )
    assert state["initial_margin_used"] == pytest.approx(position["initial_margin"])


def test_close_updates_each_venue_balance_with_its_own_leg_net_pnl(tmp_path):
    symbol = "ETH/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: [_book(99.9, 100.0), _book(101.0, 101.1, timestamp=1_001_000)]}),
        "rich": FakePublicClient({symbol: [_book(102.0, 102.1), _book(100.9, 101.0, timestamp=1_001_000)]}),
    }
    state = _default_state(20.0, clients)
    before = dict(state["venue_balances"])

    _run(tmp_path, clients=clients, symbols=[symbol], state=state)
    entry = dict(state["open_positions"][0])
    _run(
        tmp_path,
        clients=clients,
        symbols=[symbol],
        state=state,
        now_ms=1_001_000,
        now_utc="2026-08-27T12:00:01+00:00",
    )

    close = state["last_close"]
    long_entry_fee = entry["long_entry_notional"] * entry["long_fee_bps"] / 10_000.0
    short_entry_fee = entry["short_entry_notional"] * entry["short_fee_bps"] / 10_000.0
    long_exit_fee = entry["quantity"] * close["long_exit_vwap"] * entry["long_fee_bps"] / 10_000.0
    short_exit_fee = entry["quantity"] * close["short_exit_vwap"] * entry["short_fee_bps"] / 10_000.0
    long_net = entry["quantity"] * (close["long_exit_vwap"] - entry["long_entry_vwap"]) - long_entry_fee - long_exit_fee
    short_net = entry["quantity"] * (entry["short_entry_vwap"] - close["short_exit_vwap"]) - short_entry_fee - short_exit_fee

    assert state["open_positions"] == []
    assert state["venue_balances"]["cheap"] == pytest.approx(before["cheap"] + long_net)
    assert state["venue_balances"]["rich"] == pytest.approx(before["rich"] + short_net)
    assert state["equity"] == pytest.approx(sum(state["venue_balances"].values()))
    assert close["long_realized_net_pnl"] == pytest.approx(long_net)
    assert close["short_realized_net_pnl"] == pytest.approx(short_net)


def test_radar_explains_edge_below_minimum(tmp_path):
    symbol = "BNB/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0)}),
        "rich": FakePublicClient({symbol: _book(100.08, 100.18)}),
    }
    state = _default_state(20.0, clients)

    _run(tmp_path, clients=clients, symbols=[symbol], state=state, min_edge=10.0)

    assert state["open_positions"] == []
    row = state["opportunity_radar"][0]
    assert row["symbol"] == symbol
    assert row["decision"] in {"EDGE_BELOW_MIN", "NO_POSITIVE_EDGE"}


def test_migration_requires_flat_v13_and_preserves_realized_account():
    v13 = {
        "schema_version": "v13-arbitrage-paper-1",
        "initial_equity": 20.0,
        "equity": 19.9,
        "scan_count": 123,
        "opened_position_count": 3,
        "closed_position_count": 3,
        "realized_pnl": -0.1,
        "open_positions": [],
        "last_close": {"symbol": "BNB/USDT:USDT"},
    }

    state = migrate_v13_state(v13, ["okx", "mexc"])

    assert state["initial_equity"] == 20.0
    assert state["equity"] == 19.9
    assert state["realized_pnl"] == -0.1
    assert state["scan_count"] == 123
    assert sum(state["venue_balances"].values()) == pytest.approx(19.9)

    v13["open_positions"] = [{"position_id": "still-open"}]
    with pytest.raises(ValueError, match="flat"):
        migrate_v13_state(v13, ["okx", "mexc"])


def test_close_does_not_reopen_same_symbol_in_same_cycle(tmp_path):
    symbol = "SOL/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: [_book(99.9, 100.0), _book(99.9, 100.0, timestamp=1_005_000)]}),
        "rich": FakePublicClient({symbol: [_book(102.0, 102.1), _book(102.0, 102.1, timestamp=1_005_000)]}),
    }
    state = _default_state(20.0, clients)

    _run(tmp_path, clients=clients, symbols=[symbol], state=state, max_hold=1.0)
    assert state["opened_position_count"] == 1

    _run(
        tmp_path,
        clients=clients,
        symbols=[symbol],
        state=state,
        now_ms=1_005_000,
        now_utc="2026-08-27T12:00:05+00:00",
        max_hold=1.0,
    )

    assert state["closed_position_count"] == 1
    assert state["opened_position_count"] == 1
    assert state["open_positions"] == []
    assert state["opportunity_radar"][0]["decision"] == "CLOSED_THIS_CYCLE"


def test_v14_health_can_use_shared_writer_with_v14_schema(tmp_path):
    import json

    from scripts.run_arbitrage_paper_v13 import _write_health

    path = tmp_path / "health.json"
    _write_health(path, status="HEALTHY", schema_version="v14-arbitrage-health-1")

    assert json.loads(path.read_text())["schema_version"] == "v14-arbitrage-health-1"


def test_v14_defaults_expand_scan_and_reduce_only_the_extra_cushion():
    args = _parser().parse_args([])

    assert args.symbols == 50
    assert args.min_net_edge_bps == 1.0
    assert args.safety_buffer_bps == 1.0
    assert args.signal_min_net_edge_bps == -10.0
    assert args.max_open_positions == 6
    assert args.single_pair_gross_fraction == 0.3


def test_cycle_records_watch_signal_without_opening_negative_net_trade(tmp_path):
    symbol = "WATCH/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.99, 100.0)}),
        "rich": FakePublicClient({symbol: _book(100.03, 100.04)}),
    }
    state = _default_state(20.0, clients)

    run_cycle(
        clients=clients,
        symbols=[symbol],
        state=state,
        min_net_edge_bps=1.0,
        safety_buffer_bps=1.0,
        exit_threshold_bps=5.0,
        max_holding_seconds=3600.0,
        depth_limit=20,
        fee_bps={name: 1.0 for name in clients},
        max_book_age_ms=10_000,
        now_ms=1_000_000,
        now_utc="2026-08-27T12:00:00+00:00",
        journal_path=tmp_path / "positions.jsonl",
        signal_min_net_edge_bps=-10.0,
    )

    assert state["open_positions"] == []
    assert state["last_cycle_signal_count"] == 1
    assert state["last_cycle_tradeable_count"] == 0
    assert state["observed_signal_count"] == 1
    row = state["opportunity_radar"][0]
    assert row["decision"] == "NO_POSITIVE_EDGE"
    assert row["signal_status"] == "WATCH"
    assert row["edge_to_trade_bps"] > 0.0


def test_upgrade_v14b_state_to_c_preserves_existing_open_positions():
    state = _default_state(20.0, ["cheap", "rich"])
    state["margin_model"] = "ISOLATED_PAPER_V1"
    state.pop("portfolio_model", None)
    state.pop("maintenance_stress_rate", None)
    state.pop("margin_utilization_cap", None)
    state["open_positions"] = [{
        "position_id": "p1",
        "symbol": "AAA/USDT:USDT",
        "long_exchange": "cheap",
        "short_exchange": "rich",
        "quantity": 1.0,
        "long_entry_vwap": 100.0,
        "short_entry_vwap": 102.0,
        "long_entry_notional": 100.0,
        "short_entry_notional": 102.0,
        "long_fee_bps": 1.0,
        "short_fee_bps": 1.0,
        "entry_fees": 0.0202,
        "leverage": 2.0,
        "long_initial_margin": 50.0,
        "short_initial_margin": 51.0,
        "initial_margin": 101.0,
        "status": "OPEN",
    }]

    upgraded = _upgrade_v14b_state_to_c(state)

    assert upgraded is state
    assert state["margin_model"] == "CROSS_MARGIN_PAPER_V1"
    assert state["portfolio_model"] == "CROSS_MARGIN_OPTIMIZER_V1"
    assert state["open_positions"][0]["position_id"] == "p1"
    assert state["open_positions"][0]["margin_model"] == "CROSS_MARGIN_PAPER_V1"


def test_cross_margin_summary_shares_venue_collateral_and_marks_unrealized_pnl(tmp_path):
    symbol = "AAA/USDT:USDT"
    clients = {
        "cheap": FakePublicClient({symbol: _book(99.9, 100.0)}),
        "rich": FakePublicClient({symbol: _book(102.0, 102.1)}),
    }
    state = _default_state(20.0, clients, single_pair_gross_fraction=0.1)
    _run(tmp_path, clients=clients, symbols=[symbol], state=state)
    position = state["open_positions"][0]
    books = {
        symbol: {
            "cheap": __import__("crypto_research.arbitrage_v12", fromlist=["VenueBook"]).VenueBook(
                name="cheap", book={"bids": [[101.0, 100]], "asks": [[101.1, 100]]}, fee_bps=1.0
            ),
            "rich": __import__("crypto_research.arbitrage_v12", fromlist=["VenueBook"]).VenueBook(
                name="rich", book={"bids": [[101.0, 100]], "asks": [[101.1, 100]]}, fee_bps=1.0
            ),
        }
    }

    _refresh_cross_margin_summary(state, books)

    assert state["venue_margin_used"]["cheap"] > 0
    assert state["venue_margin_used"]["rich"] > 0
    assert state["venue_account_equity"]["cheap"] > state["venue_balances"]["cheap"]
    assert state["venue_account_equity"]["rich"] > state["venue_balances"]["rich"]
    assert state["venue_maintenance_stress"]["cheap"] > 0
    assert state["venue_margin_ratio"]["cheap"] > 1
    assert state["venue_available_margin"]["cheap"] == pytest.approx(
        max(0.0, state["venue_account_equity"]["cheap"] * state["margin_utilization_cap"] - state["venue_margin_used"]["cheap"])
    )
    assert position["margin_model"] == "CROSS_MARGIN_PAPER_V1"


def test_optimizer_penalizes_routes_that_concentrate_used_cross_margin():
    from crypto_research.arbitrage_v12 import ArbitrageOpportunity

    state = _default_state(20.0, ["a", "b", "c"], venue_concentration_penalty_bps=20.0)
    state["venue_margin_utilization"] = {"a": 0.7, "b": 0.7, "c": 0.0}
    crowded = ArbitrageOpportunity("AAA/USDT:USDT", "a", "b", 1.0, 100.0, 100.2, 20.0, 4.0, 1.0, 15.0)
    diversified = ArbitrageOpportunity("BBB/USDT:USDT", "a", "c", 1.0, 100.0, 100.2, 18.0, 4.0, 1.0, 13.0)

    assert _optimizer_score_bps(state, diversified) > _optimizer_score_bps(state, crowded)
