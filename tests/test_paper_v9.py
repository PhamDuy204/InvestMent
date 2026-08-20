from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_research.paper_v9 import PaperRuntimeV9


def _book() -> dict[str, object]:
    return {"bids": [[99.0, 1.0]], "asks": [[101.0, 1.0]]}


def _runtime(tmp_path: Path) -> PaperRuntimeV9:
    return PaperRuntimeV9(
        journal_path=tmp_path / "journal.jsonl",
        state_path=tmp_path / "state.json",
        health_path=tmp_path / "health.json",
        initial_equity=1_000.0,
        fee_bps=4.0,
        max_staleness_seconds=30.0,
    )


def test_v9_paper_runtime_rejects_stale_market_data_before_simulation(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    decision = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="stale"):
        runtime.process_decision(
            decision_time=decision,
            market_available_at=decision - timedelta(seconds=31),
            candidate_hash="engineering-smoke",
            candidate_frozen=False,
            freeze_timestamp=None,
            signal=0.2,
            target_exposure=0.1,
            target_notional=100.0,
            side="buy",
            book=_book(),
        )
    assert not (tmp_path / "journal.jsonl").exists()


def test_v9_paper_runtime_recovers_state_and_blocks_duplicate_after_restart(tmp_path) -> None:
    decision = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)
    runtime = _runtime(tmp_path)
    first = runtime.process_decision(
        decision_time=decision,
        market_available_at=decision,
        candidate_hash="engineering-smoke",
        candidate_frozen=False,
        freeze_timestamp=None,
        signal=0.2,
        target_exposure=0.1,
        target_notional=100.0,
        side="buy",
        book=_book(),
    )

    restarted = _runtime(tmp_path)
    state = restarted.recover_state()
    assert state["last_decision_id"] == first["decision_id"]
    assert state["position_exposure"] == 0.1

    with pytest.raises(ValueError, match="already recorded"):
        restarted.process_decision(
            decision_time=decision,
            market_available_at=decision,
            candidate_hash="engineering-smoke",
            candidate_frozen=False,
            freeze_timestamp=None,
            signal=0.2,
            target_exposure=0.1,
            target_notional=100.0,
            side="buy",
            book=_book(),
        )


def test_v9_paper_runtime_reports_partial_fill_unfilled_and_health(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    decision = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)
    row = runtime.process_decision(
        decision_time=decision,
        market_available_at=decision,
        candidate_hash="engineering-smoke",
        candidate_frozen=False,
        freeze_timestamp=None,
        signal=0.2,
        target_exposure=0.2,
        target_notional=250.0,
        side="buy",
        book=_book(),
    )

    fill = row["simulated_fill"]
    assert fill["filled_notional"] == 101.0
    assert fill["unfilled_notional"] == 149.0
    assert fill["unmodeled_tail"] is True
    health = json.loads((tmp_path / "health.json").read_text())
    assert health["status"] == "HEALTHY"
    assert health["execution"] == "SIMULATED_ONLY"


def test_v9_paper_source_contains_no_live_order_calls() -> None:
    path = Path("src/crypto_research/paper_v9.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {
        "new_order", "create_order", "place_order", "cancel_order", "withdraw", "transfer",
        "change_leverage", "set_leverage", "borrow", "repay",
    }
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
            if name in forbidden:
                calls.append((node.lineno, name))
    assert calls == []


def test_v9_public_book_capture_uses_public_fetch_and_causal_capture_time() -> None:
    from crypto_research.paper_v9 import capture_public_order_book

    class _PublicExchange:
        def __init__(self) -> None:
            self.calls = []

        def fetch_order_book(self, symbol, limit):
            self.calls.append((symbol, limit))
            return {
                "timestamp": 1787222700000,
                "bids": [[99.0, 2.0]],
                "asks": [[100.0, 2.0]],
            }

    captured = datetime(2026, 8, 20, 10, 45, 1, tzinfo=timezone.utc)
    exchange = _PublicExchange()
    snapshot = capture_public_order_book(exchange, "BTC/USDT:USDT", limit=20, captured_at=captured)

    assert exchange.calls == [("BTC/USDT:USDT", 20)]
    assert snapshot["event_time"] <= snapshot["available_at"]
    assert snapshot["available_at"] == captured
    assert snapshot["book"] == {"bids": [[99.0, 2.0]], "asks": [[100.0, 2.0]]}


def test_v9_paper_runner_source_contains_no_live_order_calls() -> None:
    forbidden = {
        "new_order", "create_order", "place_order", "cancel_order", "withdraw", "transfer",
        "change_leverage", "set_leverage", "borrow", "repay",
    }
    violations = []
    for path in (Path("src/crypto_research/paper_v9.py"), Path("scripts/run_v9_paper.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
                if name in forbidden:
                    violations.append((str(path), node.lineno, name))
    assert violations == []


def test_v9_paper_runner_wires_public_book_capture() -> None:
    path = Path("scripts/run_v9_paper.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "capture_public_order_book" in calls


def test_v9_public_book_default_capture_stamps_after_fetch(monkeypatch) -> None:
    import crypto_research.paper_v9 as paper_v9

    fetched = {"done": False}

    class _PublicExchange:
        def fetch_order_book(self, symbol, limit):
            fetched["done"] = True
            return {
                "timestamp": 1787220000500,
                "bids": [[99.0, 2.0]],
                "asks": [[100.0, 2.0]],
            }

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            second = 1 if fetched["done"] else 0
            return datetime(2026, 8, 20, 10, 0, second, tzinfo=timezone.utc)

    monkeypatch.setattr(paper_v9, "datetime", _Clock)
    snapshot = paper_v9.capture_public_order_book(_PublicExchange(), "BTC/USDT:USDT", limit=20)

    assert snapshot["available_at"] == datetime(2026, 8, 20, 10, 0, 1, tzinfo=timezone.utc)
