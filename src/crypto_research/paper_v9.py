"""Restartable V9 paper runtime. Execution is simulated-only by construction."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_research.l2_shadow_v8 import snapshot_from_order_book
from crypto_research.shadow_paper_v8 import ShadowPaperEngine, SimulatedBroker


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _journal_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def capture_public_order_book(
    exchange: Any, symbol: str, *, limit: int = 20, captured_at: datetime | None = None
) -> dict[str, Any]:
    """Fetch one public book and expose its causal capture boundary."""
    book = exchange.fetch_order_book(symbol, limit=limit)
    captured = _utc(captured_at or datetime.now(timezone.utc), "captured_at")
    normalized = snapshot_from_order_book(symbol, book, captured)
    event_time = datetime.fromisoformat(str(normalized["event_time"])).astimezone(timezone.utc)
    if event_time > captured:
        raise ValueError("order book event_time cannot be after capture time")
    return {
        "event_time": event_time,
        "available_at": captured,
        "captured_at": captured,
        "symbol": symbol,
        "book": {"bids": book["bids"], "asks": book["asks"]},
    }


class PaperRuntimeV9:
    """File-backed wrapper around the existing ShadowPaperEngine and SimulatedBroker."""

    def __init__(
        self,
        *,
        journal_path: str | Path,
        state_path: str | Path,
        health_path: str | Path,
        initial_equity: float,
        fee_bps: float = 0.0,
        max_staleness_seconds: float = 30.0,
    ) -> None:
        if initial_equity <= 0.0:
            raise ValueError("initial_equity must be positive")
        if max_staleness_seconds < 0.0:
            raise ValueError("max_staleness_seconds must be non-negative")
        self.journal_path = Path(journal_path)
        self.state_path = Path(state_path)
        self.health_path = Path(health_path)
        self.initial_equity = float(initial_equity)
        self.max_staleness_seconds = float(max_staleness_seconds)
        self.engine = ShadowPaperEngine(
            broker=SimulatedBroker(fee_bps=fee_bps), journal_path=self.journal_path
        )

    def recover_state(self) -> dict[str, Any]:
        decisions = [row for row in _journal_rows(self.journal_path) if row.get("record_type") == "DECISION"]
        outcomes = [row for row in _journal_rows(self.journal_path) if row.get("record_type") == "OUTCOME"]
        equity = self.initial_equity
        for row in outcomes:
            equity *= 1.0 + float(row.get("paper_pnl_return", 0.0))
        last = decisions[-1] if decisions else None
        filled = sum(float(row["simulated_fill"]["filled_notional"]) for row in decisions)
        unfilled = sum(float(row["simulated_fill"]["unfilled_notional"]) for row in decisions)
        fee_notional = sum(
            float(row["simulated_fill"]["filled_notional"])
            * float(row["simulated_fill"].get("fee_bps", 0.0))
            / 10_000.0
            for row in decisions
        )
        return {
            "schema_version": "v9-paper-state-1",
            "initial_equity": self.initial_equity,
            "equity": equity,
            "realized_pnl_return": equity / self.initial_equity - 1.0,
            "unrealized_pnl_return": 0.0,
            "position_exposure": float(last["target_exposure"]) if last else 0.0,
            "last_decision_id": last.get("decision_id") if last else None,
            "decision_count": len(decisions),
            "outcome_count": len(outcomes),
            "filled_notional_total": filled,
            "unfilled_notional_total": unfilled,
            "simulated_fee_notional_total": fee_notional,
            "last_funding_rate": float(last.get("funding_rate", 0.0)) if last else 0.0,
        }

    def _health(self, status: str, **extra: Any) -> None:
        _atomic_json(
            self.health_path,
            {
                "schema_version": "v9-paper-health-1",
                "status": status,
                "execution": "SIMULATED_ONLY",
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                **extra,
            },
        )

    def process_decision(
        self,
        *,
        decision_time: datetime,
        market_available_at: datetime,
        candidate_hash: str,
        candidate_frozen: bool,
        freeze_timestamp: datetime | None,
        signal: float,
        target_exposure: float,
        target_notional: float,
        side: str,
        book: dict[str, object],
        funding_rate: float = 0.0,
        decision_mid: float | None = None,
        latency_ms: int = 0,
    ) -> dict[str, Any]:
        decision = _utc(decision_time, "decision_time")
        available = _utc(market_available_at, "market_available_at")
        age = (decision - available).total_seconds()
        if age < 0.0:
            self._health("BLOCKED_FUTURE_DATA", market_age_seconds=age)
            raise ValueError("market data cannot be available after decision time")
        if age > self.max_staleness_seconds:
            self._health("BLOCKED_STALE_DATA", market_age_seconds=age)
            raise ValueError("stale market data blocks paper action")

        try:
            row = self.engine.record_decision(
                timestamp=decision,
                candidate_hash=candidate_hash,
                candidate_frozen=candidate_frozen,
                freeze_timestamp=freeze_timestamp,
                signal=signal,
                target_exposure=target_exposure,
                target_notional=target_notional,
                side=side,
                book=book,
                funding_rate=funding_rate,
                decision_mid=decision_mid,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            self._health("BLOCKED_ERROR", error_type=type(exc).__name__)
            raise
        state = self.recover_state()
        _atomic_json(self.state_path, state)
        self._health("HEALTHY", last_decision_id=row["decision_id"])
        return row
