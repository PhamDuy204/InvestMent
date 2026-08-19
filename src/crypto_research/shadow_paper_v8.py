"""Local-only V8 shadow paper journal backed by the observed-book simulator."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from crypto_research.execution_v8 import ExecutionSimulatorV8


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class SimulatedBroker:
    """Thin adapter around ExecutionSimulatorV8; it has no exchange client."""

    def __init__(self, *, fee_bps: float = 0.0) -> None:
        self.simulator = ExecutionSimulatorV8(fee_bps=fee_bps)

    def simulate(
        self,
        *,
        target_notional: float,
        side: str,
        book: dict[str, object],
        decision_mid: float | None = None,
        latency_ms: int = 0,
    ) -> dict[str, Any]:
        return asdict(
            self.simulator.simulate_market_order(
                target_notional=target_notional,
                side=side,
                book=book,
                decision_mid=decision_mid,
                latency_ms=latency_ms,
            )
        )


class ShadowPaperEngine:
    def __init__(self, *, broker: SimulatedBroker, journal_path: Path) -> None:
        self.broker = broker
        self.journal_path = Path(journal_path)

    def record_decision(
        self,
        *,
        timestamp: datetime,
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
        observed = _utc(timestamp, "timestamp")
        if not candidate_hash.strip():
            raise ValueError("candidate_hash must be non-empty")
        if candidate_frozen:
            if freeze_timestamp is None:
                raise ValueError("freeze_timestamp required for frozen candidate")
            freeze = _utc(freeze_timestamp, "freeze_timestamp")
            if observed < freeze:
                raise ValueError("freeze_timestamp must be <= decision timestamp")
            evidence_class = "FORWARD_A1_ELIGIBLE"
        else:
            if freeze_timestamp is not None:
                raise ValueError("freeze_timestamp must be absent for unfrozen candidate")
            freeze = None
            evidence_class = "ENGINEERING_ONLY"

        fill = self.broker.simulate(
            target_notional=target_notional,
            side=side,
            book=book,
            decision_mid=decision_mid,
            latency_ms=latency_ms,
        )
        identity = json.dumps(
            {
                "timestamp": observed.isoformat(),
                "candidate_hash": candidate_hash,
                "signal": float(signal),
                "target_exposure": float(target_exposure),
                "target_notional": float(target_notional),
                "side": side,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        decision_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if any(row.get("decision_id") == decision_id for row in _rows(self.journal_path)):
            raise ValueError("decision already recorded")
        row: dict[str, Any] = {
            "record_type": "DECISION",
            "decision_id": decision_id,
            "timestamp": observed.isoformat(),
            "candidate_hash": candidate_hash,
            "candidate_frozen": bool(candidate_frozen),
            "freeze_timestamp": freeze.isoformat() if freeze is not None else None,
            "signal": float(signal),
            "target_exposure": float(target_exposure),
            "target_notional": float(target_notional),
            "side": side,
            "funding_rate": float(funding_rate),
            "execution_type": "SIMULATED_FILL_ONLY",
            "simulated_fill": fill,
            "evidence_class": evidence_class,
        }
        _append_jsonl(self.journal_path, row)
        return row

    def append_outcome(
        self,
        *,
        decision_id: str,
        evaluated_at: datetime,
        horizon_hours: int,
        realized_future_return: float,
    ) -> dict[str, Any]:
        if horizon_hours <= 0:
            raise ValueError("horizon_hours must be positive")
        evaluated = _utc(evaluated_at, "evaluated_at")
        rows = _rows(self.journal_path)
        matches = [
            row
            for row in rows
            if row.get("record_type") == "DECISION" and row.get("decision_id") == decision_id
        ]
        if len(matches) != 1:
            raise ValueError("decision_id must reference exactly one decision")
        if any(row.get("record_type") == "OUTCOME" and row.get("decision_id") == decision_id for row in rows):
            raise ValueError("outcome already recorded")
        decision = matches[0]
        started = datetime.fromisoformat(str(decision["timestamp"])).astimezone(timezone.utc)
        if evaluated < started + timedelta(hours=horizon_hours):
            raise ValueError("outcome cannot be appended before horizon matures")
        fill = decision["simulated_fill"]
        exposure = float(decision["target_exposure"])
        funding = float(decision.get("funding_rate", 0.0))
        execution_cost = abs(exposure) * float(fill["total_cost_bps"]) / 10_000.0
        paper_pnl_return = exposure * float(realized_future_return) - abs(exposure) * funding - execution_cost
        row: dict[str, Any] = {
            "record_type": "OUTCOME",
            "decision_id": decision_id,
            "evaluated_at": evaluated.isoformat(),
            "horizon_hours": int(horizon_hours),
            "realized_future_return": float(realized_future_return),
            "paper_pnl_return": float(paper_pnl_return),
            "evidence_class": decision["evidence_class"],
        }
        _append_jsonl(self.journal_path, row)
        return row
