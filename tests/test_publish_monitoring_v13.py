from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.publish_monitoring_v13 as publisher
from scripts.publish_monitoring_v13 import (
    DEFAULT_INTERVAL_SECONDS,
    enrich_payload_with_live_marks,
    load_payload,
    publish_once,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_payload_without_positions_file(tmp_path):
    _write_json(
        tmp_path / "state.json",
        {
            "initial_equity": 20.0,
            "equity": 20.0,
            "realized_pnl": 0.0,
            "scan_count": 12,
            "opened_position_count": 0,
            "closed_position_count": 0,
            "open_positions": [],
        },
    )
    _write_json(
        tmp_path / "health.json",
        {"status": "HEALTHY", "error": None},
    )

    payload = load_payload(tmp_path, updated_at_utc="2026-08-27T09:30:00+00:00")

    assert payload["equity"] == 20.0
    assert payload["scan_count"] == 12
    assert payload["runner_health"] == "HEALTHY"
    assert payload["closed_positions"] == []


def test_load_payload_skips_malformed_jsonl_lines(tmp_path):
    _write_json(
        tmp_path / "state.json",
        {
            "initial_equity": 20.0,
            "equity": 20.2,
            "realized_pnl": 0.2,
            "scan_count": 20,
            "opened_position_count": 1,
            "closed_position_count": 1,
            "open_positions": [],
        },
    )
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    (tmp_path / "positions.jsonl").write_text(
        "not-json\n"
        + json.dumps(
            {
                "record_type": "PAPER_POSITION_CLOSE",
                "position_id": "p1",
                "symbol": "BTC/USDT:USDT",
                "long_exchange": "okx",
                "short_exchange": "mexc",
                "quantity": 0.001,
                "held_seconds": 60,
                "exit_fees": 0.01,
                "realized_net_pnl": 0.2,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_payload(tmp_path)

    assert payload["metrics"]["closed_trade_count"] == 1
    assert payload["realized_pnl"] == pytest.approx(0.2)


def test_publish_failure_does_not_mutate_artifacts(tmp_path):
    state_path = tmp_path / "state.json"
    health_path = tmp_path / "health.json"
    _write_json(
        state_path,
        {
            "initial_equity": 20.0,
            "equity": 20.0,
            "realized_pnl": 0.0,
            "scan_count": 5,
            "opened_position_count": 0,
            "closed_position_count": 0,
            "open_positions": [],
        },
    )
    _write_json(health_path, {"status": "HEALTHY", "error": None})
    before = (_sha256(state_path), _sha256(health_path))

    def failing_opener(*args, **kwargs):
        raise OSError("network down")

    ok = publish_once(
        artifacts_dir=tmp_path,
        ingest_url="https://example.invalid/api/ingest",
        ingest_token="test-token",
        opener=failing_opener,
    )

    after = (_sha256(state_path), _sha256(health_path))
    assert ok is False
    assert after == before


def test_enrich_payload_with_live_marks_fetches_public_close_books():
    payload = {
        "equity": 20.0,
        "open_positions": [
            {
                "position_id": "p1",
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
        ],
    }

    class Client:
        def __init__(self, book):
            self.book = book
            self.calls = []

        def fetch_order_book(self, symbol, limit=20):
            self.calls.append((symbol, limit))
            return self.book

    okx = Client({"bids": [[101.0, 2.0]], "asks": [[101.1, 2.0]]})
    mexc = Client({"bids": [[101.4, 2.0]], "asks": [[101.5, 2.0]]})

    enrich_payload_with_live_marks(
        payload,
        {"okx": okx, "mexc": mexc},
        marked_at_utc="2026-08-27T09:10:00+00:00",
    )

    marked = payload["open_positions"][0]
    assert marked["mark_status"] == "LIVE"
    assert marked["estimated_net_pnl_if_closed"] == pytest.approx(1.2367)
    assert marked["exposure_pct_of_equity"] == pytest.approx((202.0 / 20.0) * 100)
    assert okx.calls == [("BNB/USDT:USDT", 20)]
    assert mexc.calls == [("BNB/USDT:USDT", 20)]


def test_enrich_v14_unavailable_mark_does_not_erase_modeled_margin():
    payload = {
        "equity": 20.0,
        "open_positions": [
            {
                "position_id": "p1",
                "symbol": "BNB/USDT:USDT",
                "long_exchange": "missing",
                "short_exchange": "mexc",
                "quantity": 1.0,
                "margin_model": "ISOLATED_PAPER_V1",
                "leverage": 2.0,
                "initial_margin": 5.0,
            }
        ],
    }

    enrich_payload_with_live_marks(payload, {})

    marked = payload["open_positions"][0]
    assert marked["mark_status"] == "UNAVAILABLE"
    assert marked["margin_model"] == "ISOLATED_PAPER_V1"
    assert marked["leverage"] == 2.0
    assert marked["initial_margin"] == 5.0


def test_publisher_default_interval_is_two_seconds():
    assert DEFAULT_INTERVAL_SECONDS == 2.0


def test_load_payload_promotes_v14_to_v15_only_when_valid_shadow_file_exists(tmp_path):
    _write_json(
        tmp_path / "state.json",
        {
            "schema_version": "v14-arbitrage-paper-1",
            "initial_equity": 20.0,
            "equity": 20.0,
            "realized_pnl": 0.0,
            "scan_count": 1,
            "opened_position_count": 0,
            "closed_position_count": 0,
            "open_positions": [],
        },
    )
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    _write_json(
        tmp_path / "shadow_v15.json",
        {
            "schema_version": "v15-shadow-paper-1",
            "updated_at_utc": "2026-08-27T13:00:00+00:00",
            "strategy_lab": {},
            "radar_diagnostics": {},
        },
    )

    assert load_payload(tmp_path)["schema_version"] == "v15-monitoring-1"

    (tmp_path / "shadow_v15.json").unlink()
    assert load_payload(tmp_path)["schema_version"] == "v14-monitoring-1"


def test_load_payload_reads_bounded_v16_monitor_history(tmp_path):
    from crypto_research.route_v16 import record_monitor_snapshot

    _write_json(
        tmp_path / "state.json",
        {
            "schema_version": "v16-arbitrage-paper-1",
            "initial_equity": 100.0,
            "equity": 100.0,
            "realized_pnl": 0.0,
            "scan_count": 5,
            "opened_position_count": 1,
            "closed_position_count": 0,
            "open_positions": [],
            "margin_model": "CROSS_MARGIN_PAPER_V1",
            "portfolio_model": "ROUTE_RELATIVE_MULTI_STRATEGY_V1",
            "exchange_leverage": 3.0,
            "gross_leverage_cap": 2.0,
            "max_open_positions": 8,
            "single_pair_gross_fraction": 0.2,
            "universe_symbols": ["AAA/USDT:USDT"],
        },
    )
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    record_monitor_snapshot(
        tmp_path / "history_v16.sqlite",
        now_ms=1_000_000,
        account={
            "realized_equity": 100.0,
            "marked_equity": 99.9,
            "realized_pnl": 0.0,
            "unrealized_net_pnl": -0.1,
            "gross_exposure": 20.0,
            "margin_used": 7.0,
            "modeled_fee_drag": 0.03,
        },
        positions=[{
            "position_id": "p16",
            "symbol": "AAA/USDT:USDT",
            "spread_bps": 10.0,
            "net_pnl": -0.1,
            "baseline_bps": 5.0,
        }],
    )

    payload = load_payload(tmp_path, updated_at_utc="2026-08-28T00:00:01+00:00")
    assert payload["schema_version"] == "v16-monitoring-1"
    assert payload["account_history"][0]["marked_equity"] == pytest.approx(99.9)
    assert payload["position_history"]["p16"][0]["baseline_bps"] == pytest.approx(5.0)


def test_load_payload_reads_v17_history_and_schema(tmp_path):
    from crypto_research.route_v16 import record_monitor_snapshot

    _write_json(tmp_path / "state.json", {
        "schema_version": "v17-arbitrage-paper-1",
        "initial_equity": 100.0, "equity": 100.0, "realized_pnl": 0.0, "scan_count": 3,
        "opened_position_count": 0, "closed_position_count": 0, "open_positions": [],
        "pending_entries": [], "pending_exits": [],
        "margin_model": "CROSS_MARGIN_PAPER_V1", "portfolio_model": "MAKER_FIRST_EV_MULTI_STRATEGY_V1",
        "exchange_leverage": 3.0, "gross_leverage_cap": 2.0, "max_open_positions": 8,
        "single_pair_gross_fraction": 0.2, "universe_symbols": ["AAA/USDT:USDT"],
    })
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    record_monitor_snapshot(
        tmp_path / "history_v17.sqlite", now_ms=2_000_000,
        account={"realized_equity": 100.0, "marked_equity": 100.0, "realized_pnl": 0.0,
                 "unrealized_net_pnl": 0.0, "gross_exposure": 0.0, "margin_used": 0.0, "modeled_fee_drag": 0.0},
        positions=[],
    )
    payload = load_payload(tmp_path, updated_at_utc="2026-08-28T03:02:00+00:00")
    assert payload["schema_version"] == "v17-monitoring-1"
    assert payload["account_history"][0]["realized_equity"] == pytest.approx(100.0)


def test_load_payload_reads_v18_history_and_schema(tmp_path):
    from crypto_research.route_v16 import record_monitor_snapshot

    _write_json(tmp_path / "state.json", {
        "schema_version": "v18-arbitrage-paper-1",
        "initial_equity": 100.0, "equity": 100.0, "realized_pnl": 0.0, "scan_count": 1,
        "opened_position_count": 0, "closed_position_count": 0, "open_positions": [],
        "pending_entries": [], "pending_exits": [], "margin_model": "CROSS_MARGIN_PAPER_V1",
        "portfolio_model": "WS_CAUSAL_POST_FILL_EV_V1", "exchange_leverage": 40.0,
        "gross_leverage_cap": 40.0, "max_open_positions": 8,
        "single_pair_gross_fraction": 4.0, "universe_symbols": ["AAA/USDT:USDT"],
    })
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    record_monitor_snapshot(
        tmp_path / "history_v18.sqlite", now_ms=3_000_000,
        account={"realized_equity": 100.0, "marked_equity": 100.0, "realized_pnl": 0.0,
                 "unrealized_net_pnl": 0.0, "gross_exposure": 0.0, "margin_used": 0.0,
                 "modeled_fee_drag": 0.0},
        positions=[],
    )

    payload = load_payload(tmp_path, updated_at_utc="2026-08-28T05:00:00+00:00")

    assert payload["schema_version"] == "v18-monitoring-1"
    assert payload["account_history"][0]["realized_equity"] == pytest.approx(100.0)


def test_load_payload_reads_v19_history_and_schema(tmp_path):
    from crypto_research.route_v16 import record_monitor_snapshot

    _write_json(tmp_path / "state.json", {
        "schema_version": "v19-arbitrage-paper-1",
        "initial_equity": 100.0, "equity": 100.0, "realized_pnl": 0.0, "scan_count": 1,
        "opened_position_count": 0, "closed_position_count": 0, "open_positions": [],
        "pending_entries": [], "pending_exits": [], "margin_model": "CROSS_MARGIN_PAPER_V1",
        "portfolio_model": "WS_CAUSAL_POST_FILL_EV_V2", "exchange_leverage": 40.0,
        "gross_leverage_cap": 40.0, "max_open_positions": 8,
        "single_pair_gross_fraction": 4.0, "universe_symbols": ["AAA/USDT:USDT"],
        "candidate_funnel_counts": {},
    })
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    record_monitor_snapshot(
        tmp_path / "history_v19.sqlite", now_ms=4_000_000,
        account={"realized_equity": 100.0, "marked_equity": 100.0, "realized_pnl": 0.0,
                 "unrealized_net_pnl": 0.0, "gross_exposure": 0.0, "margin_used": 0.0,
                 "modeled_fee_drag": 0.0},
        positions=[],
    )

    payload = load_payload(tmp_path, updated_at_utc="2026-08-28T06:00:00+00:00")

    assert payload["schema_version"] == "v19-monitoring-1"
    assert payload["account_history"][0]["observed_at_ms"] == 4_000_000


def test_v19_publisher_uses_persisted_marks_without_public_rest_clients(
    monkeypatch,
    tmp_path,
):
    _write_json(tmp_path / "state.json", {"schema_version": "v19-arbitrage-paper-1"})
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    monkeypatch.setenv("MONITOR_INGEST_URL", "https://example.invalid/api/ingest")
    monkeypatch.setenv("MONITOR_INGEST_TOKEN", "token")
    monkeypatch.setattr(
        publisher,
        "make_public_clients",
        lambda **kwargs: pytest.fail("V19 must not construct separate REST clients"),
    )
    observed = {}

    def fake_publish_once(**kwargs):
        observed.update(kwargs)
        return True

    monkeypatch.setattr(publisher, "publish_once", fake_publish_once)
    monkeypatch.setattr(
        "sys.argv",
        ["publish_monitoring_v13.py", "--artifacts-dir", str(tmp_path), "--once"],
    )

    assert publisher.main() == 0
    assert observed["clients"] is None


def test_v21_publisher_uses_persisted_marks_without_public_rest_clients(monkeypatch, tmp_path):
    _write_json(tmp_path / "state.json", {"schema_version": "v21-arbitrage-paper-1"})
    _write_json(tmp_path / "health.json", {"status": "HEALTHY", "error": None})
    monkeypatch.setenv("MONITOR_INGEST_URL", "https://example.invalid/api/ingest")
    monkeypatch.setenv("MONITOR_INGEST_TOKEN", "token")
    monkeypatch.setattr(
        publisher,
        "make_public_clients",
        lambda **kwargs: pytest.fail("V21 must not construct separate REST clients"),
    )
    observed = {}

    def fake_publish_once(**kwargs):
        observed.update(kwargs)
        return True

    monkeypatch.setattr(publisher, "publish_once", fake_publish_once)
    monkeypatch.setattr(
        "sys.argv",
        ["publish_monitoring_v13.py", "--artifacts-dir", str(tmp_path), "--once"],
    )

    assert publisher.main() == 0
    assert observed["clients"] is None
