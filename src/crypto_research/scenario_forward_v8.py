"""Append-only forward scenario registry for MiroFish/OASIS V8 research."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def lock_forward_scenario(
    registry: Path,
    *,
    scenario_id: str,
    created_at: datetime,
    seed_cutoff_time: datetime,
    seed_packet: dict[str, Any],
    source_hashes: list[str],
    model: str,
    mirofish_commit: str,
    personas: list[str],
    prediction_horizon_hours: int,
    prediction: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    registry = Path(registry)
    created = _utc(created_at, "created_at")
    cutoff = _utc(seed_cutoff_time, "seed_cutoff_time")
    if not scenario_id.strip():
        raise ValueError("scenario_id must be non-empty")
    if cutoff > created:
        raise ValueError("seed_cutoff_time must be <= created_at")
    if prediction_horizon_hours <= 0:
        raise ValueError("prediction_horizon_hours must be positive")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    existing = _read_rows(registry)
    if any(row.get("record_type") == "PREDICTION" and row.get("scenario_id") == scenario_id for row in existing):
        raise ValueError(f"scenario_id already exists: {scenario_id}")

    seed_canonical = json.dumps(seed_packet, sort_keys=True, separators=(",", ":"), default=str)
    row: dict[str, Any] = {
        "record_type": "PREDICTION",
        "scenario_id": scenario_id,
        "created_at": created.isoformat(),
        "seed_cutoff_time": cutoff.isoformat(),
        "seed_hash": hashlib.sha256(seed_canonical.encode("utf-8")).hexdigest(),
        "source_hashes": sorted(source_hashes),
        "model": model,
        "mirofish_commit": mirofish_commit,
        "personas": personas,
        "prediction_horizon_hours": int(prediction_horizon_hours),
        "prediction": prediction,
        "confidence": float(confidence),
        "actual_evaluation_deadline": (created + timedelta(hours=prediction_horizon_hours)).isoformat(),
        "locked": True,
        "status": "SCENARIO_RESEARCH_ONLY",
    }
    _append_jsonl(registry, row)
    return row


def append_scenario_evaluation(
    registry: Path,
    *,
    scenario_id: str,
    evaluated_at: datetime,
    actual_outcome: dict[str, Any],
    score: dict[str, Any],
) -> dict[str, Any]:
    registry = Path(registry)
    evaluated = _utc(evaluated_at, "evaluated_at")
    rows = _read_rows(registry)
    predictions = [
        row
        for row in rows
        if row.get("record_type") == "PREDICTION" and row.get("scenario_id") == scenario_id
    ]
    if len(predictions) != 1:
        raise ValueError("scenario prediction must exist exactly once")
    if any(row.get("record_type") == "EVALUATION" and row.get("scenario_id") == scenario_id for row in rows):
        raise ValueError("scenario evaluation already exists")
    deadline = datetime.fromisoformat(str(predictions[0]["actual_evaluation_deadline"]))
    deadline = deadline.astimezone(timezone.utc)
    if evaluated < deadline:
        raise ValueError("evaluation cannot be appended before actual evaluation deadline")
    row: dict[str, Any] = {
        "record_type": "EVALUATION",
        "scenario_id": scenario_id,
        "evaluated_at": evaluated.isoformat(),
        "actual_outcome": actual_outcome,
        "score": score,
    }
    _append_jsonl(registry, row)
    return row
