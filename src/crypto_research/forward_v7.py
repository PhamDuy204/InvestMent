from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hashed_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_config": payload["candidate_config"],
        "source_sha": payload["source_sha"],
        "causal_schema_version": payload["causal_schema_version"],
        "total_trial_count_at_freeze": int(payload["total_trial_count_at_freeze"]),
    }


def _state_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_hashed_state(payload)).encode()).hexdigest()


def _payload_verifies(payload: dict[str, Any]) -> bool:
    required = {
        "candidate_config",
        "source_sha",
        "causal_schema_version",
        "total_trial_count_at_freeze",
        "candidate_hash_sha256",
    }
    if required.difference(payload):
        return False
    return str(payload["candidate_hash_sha256"]) == _state_hash(payload)


def freeze_v7_candidate(
    config: dict[str, object],
    *,
    artifact_root: str | Path,
    timestamp: str,
    total_trial_count: int,
    source_sha: str,
    causal_schema_version: str,
) -> dict[str, Any]:
    if total_trial_count < 857:
        raise ValueError("V7 freeze trial count cannot precede the inherited 857 trials")
    if not str(source_sha).strip() or not str(causal_schema_version).strip():
        raise ValueError("source_sha and causal_schema_version are required")
    freeze_timestamp = pd.Timestamp(timestamp)
    freeze_timestamp = (
        freeze_timestamp.tz_localize("UTC")
        if freeze_timestamp.tzinfo is None
        else freeze_timestamp.tz_convert("UTC")
    )
    payload: dict[str, Any] = {
        "research_version": "V7",
        "freeze_timestamp_utc": freeze_timestamp.isoformat(),
        "candidate_config": config,
        "source_sha": str(source_sha),
        "causal_schema_version": str(causal_schema_version),
        "total_trial_count_at_freeze": int(total_trial_count),
        "locked_evidence": {
            "2021_2023": "OBSERVED_LOCKED_NOT_FOR_V7_SELECTION",
            "2026_08_01_to_10": "OBSERVED_LOCKED_NOT_FOR_V7_SELECTION",
        },
    }
    payload["candidate_hash_sha256"] = _state_hash(payload)
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "forward_freeze.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return payload


def verify_v7_freeze(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return _payload_verifies(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def evaluate_a1_readiness(
    forward: pd.DataFrame,
    freeze: dict[str, Any],
    *,
    candidate_hash: str,
    ret_10bps: float,
    profit_factor: float,
    sharpe: float,
    ret_20bps: float,
    delay_1h_return: float,
    liquidation_count: int,
    exposure_violation_count: int,
    margin_violation_count: int,
    forward_driven_retuning: bool,
) -> dict[str, Any]:
    if "decision_timestamp" not in forward.columns:
        raise ValueError("forward observations require decision_timestamp")
    work = forward.copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    if "eligible_h12" in work.columns:
        work = work.loc[work["eligible_h12"].fillna(False).astype(bool)].copy()
    freeze_timestamp = pd.Timestamp(freeze["freeze_timestamp_utc"])
    freeze_timestamp = (
        freeze_timestamp.tz_localize("UTC")
        if freeze_timestamp.tzinfo is None
        else freeze_timestamp.tz_convert("UTC")
    )
    post = work.loc[work["decision_timestamp"] > freeze_timestamp].sort_values("decision_timestamp")
    observations = int(len(post))
    if observations:
        first_day = post["decision_timestamp"].iloc[0].floor("D")
        last_day = post["decision_timestamp"].iloc[-1].floor("D")
        calendar_days = int((last_day - first_day).days + 1)
    else:
        calendar_days = 0

    failed: list[str] = []
    if calendar_days < 30:
        failed.append("minimum_calendar_days")
    if observations < 40:
        failed.append("minimum_h12_observations")
    if float(ret_10bps) <= 0.0:
        failed.append("positive_10bps")
    if float(profit_factor) <= 1.10:
        failed.append("profit_factor_gt_1_10")
    if float(sharpe) <= 0.50:
        failed.append("sharpe_gt_0_50")
    if float(ret_20bps) < 0.0:
        failed.append("nonnegative_20bps")
    if float(delay_1h_return) < 0.0:
        failed.append("nonnegative_delay_1h")
    if int(liquidation_count) != 0:
        failed.append("zero_liquidation")
    if int(exposure_violation_count) != 0:
        failed.append("zero_exposure_violations")
    if int(margin_violation_count) != 0:
        failed.append("zero_margin_violations")
    if not _payload_verifies(freeze) or str(candidate_hash) != str(freeze.get("candidate_hash_sha256", "")):
        failed.append("candidate_hash_unchanged")
    if bool(forward_driven_retuning):
        failed.append("zero_forward_driven_retuning")

    verdict = "READY_FOR_PAPER_TRADING" if not failed else "NEEDS_MORE_RESEARCH"
    return {
        "verdict": verdict,
        "failed_gates": failed,
        "calendar_days": calendar_days,
        "eligible_h12_observations": observations,
        "candidate_hash_sha256": str(candidate_hash),
        "freeze_hash_verified": bool(_payload_verifies(freeze)),
        "metrics": {
            "ret_10bps": float(ret_10bps),
            "profit_factor": float(profit_factor),
            "sharpe": float(sharpe),
            "ret_20bps": float(ret_20bps),
            "delay_1h_return": float(delay_1h_return),
            "liquidation_count": int(liquidation_count),
            "exposure_violation_count": int(exposure_violation_count),
            "margin_violation_count": int(margin_violation_count),
            "forward_driven_retuning": bool(forward_driven_retuning),
        },
    }
