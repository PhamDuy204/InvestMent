from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd


def _normalize(text: object) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def mechanism_fingerprint(
    target_error: str,
    expected_mechanism: str,
    causal_inputs: list[str],
    action: str,
) -> str:
    payload = {
        "target_error": _normalize(target_error),
        "expected_mechanism": _normalize(expected_mechanism),
        "causal_inputs": sorted(_normalize(item) for item in causal_inputs),
        "action": _normalize(action),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def build_failure_record(
    *,
    trial_number: int,
    hypothesis: str,
    target_error: str,
    expected_mechanism: str,
    causal_inputs: list[str],
    action: str,
    actual_error_delta: int,
    net_effect_bps: float,
    turnover_effect: float,
    drawdown_effect: float,
    damaged_regime: str,
    helped_regime: str,
    assumption_status: str,
    failure_reason: str,
    next_allowed_question: str,
    timestamp_utc: str,
) -> dict[str, object]:
    fingerprint = mechanism_fingerprint(
        target_error,
        expected_mechanism,
        causal_inputs,
        action,
    )
    return {
        "trial_number": int(trial_number),
        "hypothesis": str(hypothesis),
        "timestamp_utc": str(timestamp_utc),
        "target_error": str(target_error),
        "expected_mechanism": str(expected_mechanism),
        "causal_inputs_json": json.dumps(sorted(str(item) for item in causal_inputs)),
        "action": str(action),
        "actual_error_delta": int(actual_error_delta),
        "net_effect_bps": float(net_effect_bps),
        "turnover_effect": float(turnover_effect),
        "drawdown_effect": float(drawdown_effect),
        "damaged_regime": str(damaged_regime),
        "helped_regime": str(helped_regime),
        "assumption_status": str(assumption_status),
        "failure_reason": str(failure_reason),
        "do_not_repeat_fingerprint": fingerprint,
        "next_allowed_question": str(next_allowed_question),
    }


def append_failure_ledger(records: list[dict[str, object]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        if not target.exists():
            pd.DataFrame().to_csv(target, index=False, compression="gzip")
        return target
    frame = pd.DataFrame(records)
    exists = target.exists() and target.stat().st_size > 0
    frame.to_csv(
        target,
        mode="a" if exists else "w",
        header=not exists,
        index=False,
        compression="gzip",
    )
    return target


def write_do_not_repeat(records: list[dict[str, object]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    by_fingerprint: dict[str, str] = {}
    for record in records:
        fingerprint = str(record.get("do_not_repeat_fingerprint", "")).strip()
        if not fingerprint:
            continue
        by_fingerprint.setdefault(fingerprint, str(record.get("expected_mechanism", "")))
    payload = {
        "fingerprints": sorted(by_fingerprint),
        "mechanisms": [
            {"fingerprint": fingerprint, "expected_mechanism": by_fingerprint[fingerprint]}
            for fingerprint in sorted(by_fingerprint)
        ],
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_do_not_repeat(path: str | Path) -> set[str]:
    target = Path(path)
    if not target.exists():
        return set()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return {str(item) for item in payload.get("fingerprints", [])}


def reject_repeated_mechanism(
    fingerprint: str,
    blocked: set[str],
    *,
    materially_new_evidence: bool = False,
) -> None:
    if fingerprint in blocked and not materially_new_evidence:
        raise ValueError("mechanism is blocked by V7 do-not-repeat memory")
