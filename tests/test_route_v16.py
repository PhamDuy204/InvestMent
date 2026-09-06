from pathlib import Path

import pytest

import crypto_research.route_v16 as route_v16
from crypto_research.route_v16 import (
    dynamic_leverage,
    entry_decision,
    record_route_snapshots,
    route_features,
)


def _row(gross: float, mid: float = 100.0):
    return {
        "symbol": "BNB/USDT:USDT",
        "buy_venue": "bitget",
        "sell_venue": "mexc",
        "gross_edge_bps": gross,
        "reference_mid_price": mid,
    }


def test_route_writer_uses_wal_and_waits_through_monitor_contention(tmp_path: Path):
    connection = route_v16._connect(tmp_path / "history.sqlite")
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
    finally:
        connection.close()


def test_route_sqlite_connections_close_eagerly(tmp_path: Path, monkeypatch):
    db = tmp_path / "history.sqlite"
    real_connect = route_v16.sqlite3.connect
    opened = []

    class TrackedConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def close(self):
            self.closed = True
            self.connection.close()

    def tracked_connect(*args, **kwargs):
        tracked = TrackedConnection(real_connect(*args, **kwargs))
        opened.append(tracked)
        return tracked

    monkeypatch.setattr(route_v16.sqlite3, "connect", tracked_connect)
    record_route_snapshots(db, 1_000, [_row(5.0)])

    assert opened
    assert all(connection.closed for connection in opened)


def test_structural_basis_is_rejected_after_real_fee_hurdle(tmp_path: Path):
    db = tmp_path / "history.sqlite"
    start = 1_000_000
    for i in range(80):
        gross = 37.0 + (0.2 if i % 2 else -0.2)
        record_route_snapshots(db, start + i * 15_000, [_row(gross, 700.0 + i * 0.01)])

    now = start + 80 * 15_000
    features = route_features(db, "BNB/USDT:USDT", "bitget", "mexc", now_ms=now)
    assert features is not None
    decision = entry_decision(
        current_gross_edge_bps=38.0,
        total_fee_bps=28.0,
        safety_buffer_bps=0.5,
        features=features,
    )
    assert decision["decision"] == "EXCESS_BELOW_COST"
    assert decision["tradeable"] is False
    assert decision["baseline_bps"] == pytest.approx(37.0, abs=0.3)
    assert decision["excess_spread_bps"] == pytest.approx(1.0, abs=0.3)


def test_true_route_dislocation_qualifies_only_after_turn_confirmation(tmp_path: Path):
    db = tmp_path / "history.sqlite"
    start = 2_000_000
    # Long structural baseline around zero.
    for i in range(48):
        record_route_snapshots(db, start + i * 15_000, [_row((i % 3 - 1) * 0.2, 100.0 + i * 0.01)])
    # A large dislocation spikes then starts contracting in the recent 5m window.
    spike_start = start + 48 * 15_000
    for i, gross in enumerate([68 - 0.5 * i for i in range(21)]):
        record_route_snapshots(db, spike_start + i * 15_000, [_row(gross, 100.5 + i * 0.01)])

    now = spike_start + 20 * 15_000
    features = route_features(db, "BNB/USDT:USDT", "bitget", "mexc", now_ms=now)
    assert features is not None
    decision = entry_decision(
        current_gross_edge_bps=58.0,
        total_fee_bps=20.0,
        safety_buffer_bps=0.5,
        features=features,
    )
    assert decision["decision"] == "TRADEABLE"
    assert decision["tradeable"] is True
    assert decision["excess_after_cost_bps"] > 30.0
    assert decision["short_slope_bps_per_min"] < 0.0


def test_missing_history_is_warmup_not_zero_baseline():
    decision = entry_decision(
        current_gross_edge_bps=60.0,
        total_fee_bps=20.0,
        safety_buffer_bps=0.5,
        features=None,
    )
    assert decision == {"decision": "BASELINE_WARMUP", "tradeable": False}


def test_positive_short_slope_waits_for_turn():
    features = {
        "baseline_bps": 0.0,
        "route_sigma_bps": 2.0,
        "short_slope_bps_per_min": 0.4,
        "medium_slope_bps_per_min": 0.1,
        "price_volatility_bps": 5.0,
        "sample_count": 40,
        "span_seconds": 1200.0,
    }
    decision = entry_decision(
        current_gross_edge_bps=40.0,
        total_fee_bps=20.0,
        safety_buffer_bps=0.5,
        features=features,
    )
    assert decision["decision"] == "WAITING_FOR_TURN"
    assert decision["tradeable"] is False


def test_dynamic_leverage_is_volatility_and_quality_aware():
    assert dynamic_leverage(excess_after_cost_bps=4.0, z_score=1.2, route_sigma_bps=10.0, price_volatility_bps=45.0) == 1.0
    assert dynamic_leverage(excess_after_cost_bps=8.0, z_score=1.6, route_sigma_bps=4.0, price_volatility_bps=15.0) == 2.0
    assert dynamic_leverage(excess_after_cost_bps=20.0, z_score=3.0, route_sigma_bps=3.0, price_volatility_bps=10.0) == 3.0


def test_current_rewidening_waits_even_when_historical_slope_is_negative():
    features = {
        "baseline_bps": 0.0,
        "route_sigma_bps": 2.0,
        "short_slope_bps_per_min": -0.5,
        "medium_slope_bps_per_min": -0.2,
        "price_volatility_bps": 5.0,
        "last_gross_edge_bps": 35.0,
        "sample_count": 40,
        "span_seconds": 1200.0,
    }
    decision = entry_decision(
        current_gross_edge_bps=40.0,
        total_fee_bps=20.0,
        safety_buffer_bps=0.5,
        features=features,
    )
    assert decision["decision"] == "WAITING_FOR_TURN"


def test_compact_monitor_history_records_reads_and_prunes(tmp_path: Path):
    from crypto_research.route_v16 import read_monitor_history, record_monitor_snapshot

    db = tmp_path / "history.sqlite"
    now = 10 * 60 * 60_000
    old = now - 7 * 60 * 60_000
    record_monitor_snapshot(
        db,
        now_ms=old,
        account={"realized_equity": 99.0, "marked_equity": 98.5, "realized_pnl": -1.0, "unrealized_net_pnl": -0.5, "gross_exposure": 20.0, "margin_used": 10.0, "modeled_fee_drag": 0.2},
        positions=[{"position_id": "old", "symbol": "OLD/USDT:USDT", "spread_bps": 20.0, "net_pnl": -0.2}],
        retention_ms=6 * 60 * 60_000,
    )
    record_monitor_snapshot(
        db,
        now_ms=now,
        account={"realized_equity": 100.0, "marked_equity": 100.4, "realized_pnl": 0.0, "unrealized_net_pnl": 0.4, "gross_exposure": 30.0, "margin_used": 12.0, "modeled_fee_drag": 0.1},
        positions=[{"position_id": "p1", "symbol": "BNB/USDT:USDT", "spread_bps": 15.0, "net_pnl": 0.4, "baseline_bps": 10.0}],
        retention_ms=6 * 60 * 60_000,
    )

    history = read_monitor_history(db, account_limit=10, position_limit=10)
    assert [row["observed_at_ms"] for row in history["account_history"]] == [now]
    assert history["account_history"][0]["marked_equity"] == pytest.approx(100.4)
    assert set(history["position_history"]) == {"p1"}
    assert history["position_history"]["p1"][0]["symbol"] == "BNB/USDT:USDT"
    assert history["position_history"]["p1"][0]["baseline_bps"] == pytest.approx(10.0)





def test_route_feature_read_does_not_mutate_schema(tmp_path: Path):
    import sqlite3
    import crypto_research.route_v16 as route_v16

    db = tmp_path / "history.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        """
        CREATE TABLE route_history_v16 (
            observed_at_ms INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            buy_venue TEXT NOT NULL,
            sell_venue TEXT NOT NULL,
            gross_edge_bps REAL NOT NULL,
            reference_mid_price REAL,
            PRIMARY KEY (observed_at_ms, symbol, buy_venue, sell_venue)
        )
        """
    )
    connection.executemany(
        "INSERT INTO route_history_v16 VALUES (?, 'BTC/USDT:USDT', 'okx', 'binance', ?, 50000)",
        [(i * 60_000, 10.0 + i) for i in range(12)],
    )
    connection.commit()
    connection.close()

    features = route_v16.route_features(
        db, "BTC/USDT:USDT", "okx", "binance",
        now_ms=11 * 60_000, min_samples=8, min_span_seconds=7 * 60,
    )

    connection = sqlite3.connect(db)
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    connection.close()
    assert features is not None
    assert "idx_route_history_v16_route_time" not in indexes

def test_monitor_history_read_does_not_mutate_schema(tmp_path: Path):
    import sqlite3
    import crypto_research.route_v16 as route_v16

    db = tmp_path / "history.sqlite"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE account_history_v16 (
            observed_at_ms INTEGER PRIMARY KEY,
            realized_equity REAL NOT NULL,
            marked_equity REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_net_pnl REAL NOT NULL,
            gross_exposure REAL NOT NULL,
            margin_used REAL NOT NULL,
            modeled_fee_drag REAL NOT NULL
        );
        CREATE TABLE position_history_v16 (
            observed_at_ms INTEGER NOT NULL,
            position_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            spread_bps REAL NOT NULL,
            net_pnl REAL NOT NULL,
            baseline_bps REAL,
            PRIMARY KEY (observed_at_ms, position_id)
        );
        INSERT INTO account_history_v16 VALUES (1000, 100, 100, 0, 0, 0, 0, 0);
        """
    )
    connection.commit()
    connection.close()

    history = route_v16.read_monitor_history(db)

    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert history["account_history"][0]["realized_equity"] == pytest.approx(100.0)
    assert "route_history_v16" not in tables

def test_v16_can_seed_route_baselines_from_v15_radar_history_without_copying_state(tmp_path: Path):
    import sqlite3

    from crypto_research.route_v16 import seed_route_history_from_v15

    legacy = tmp_path / "history_v15.sqlite"
    with sqlite3.connect(legacy) as connection:
        connection.execute("CREATE TABLE radar_history (observed_at_ms INTEGER, symbol TEXT, buy_venue TEXT, sell_venue TEXT, gross_edge_bps REAL, net_edge_bps REAL, PRIMARY KEY (observed_at_ms, symbol, buy_venue, sell_venue))")
        connection.executemany(
            "INSERT INTO radar_history VALUES (?, ?, ?, ?, ?, ?)",
            [(1_000_000 + i * 15_000, "BNB/USDT:USDT", "bitget", "mexc", 37.0 + (i % 2) * 0.2, 9.0) for i in range(41)],
        )
    target = tmp_path / "history_v16.sqlite"
    copied = seed_route_history_from_v15(target, legacy, now_ms=1_000_000 + 41 * 15_000)
    assert copied == 41
    assert seed_route_history_from_v15(target, legacy, now_ms=1_000_000 + 41 * 15_000) == 0
    features = route_features(target, "BNB/USDT:USDT", "bitget", "mexc", now_ms=1_000_000 + 41 * 15_000)
    assert features is not None
    assert features["baseline_bps"] == pytest.approx(37.1, abs=0.2)


def test_route_history_has_route_time_index(tmp_path: Path):
    import sqlite3

    db = tmp_path / "history.sqlite"
    record_route_snapshots(db, 1_000, [_row(1.0)])
    with sqlite3.connect(db) as connection:
        names = {row[1] for row in connection.execute("PRAGMA index_list(route_history_v16)")}
    assert "idx_route_history_v16_route_time" in names


def test_monitor_history_bounds_position_ids_and_has_position_time_index(tmp_path: Path):
    import sqlite3

    from crypto_research.route_v16 import read_monitor_history, record_monitor_snapshot

    db = tmp_path / "history.sqlite"
    account = {
        "realized_equity": 100.0,
        "marked_equity": 100.0,
        "realized_pnl": 0.0,
        "unrealized_net_pnl": 0.0,
        "gross_exposure": 0.0,
        "margin_used": 0.0,
        "modeled_fee_drag": 0.0,
    }
    for index in range(140):
        record_monitor_snapshot(
            db,
            now_ms=1_000_000 + index,
            account=account,
            positions=[
                {
                    "position_id": f"p-{index:03d}",
                    "symbol": "AAA/USDT:USDT",
                    "spread_bps": float(index),
                    "net_pnl": 0.0,
                }
            ],
        )

    history = read_monitor_history(db, account_limit=2, position_limit=2)
    assert len(history["position_history"]) == 128
    assert "p-139" in history["position_history"]
    assert "p-000" not in history["position_history"]
    with sqlite3.connect(db) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list('position_history_v16')")}
    assert "idx_position_history_v16_position_time" in indexes
