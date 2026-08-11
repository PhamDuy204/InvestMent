from __future__ import annotations

import re
from dataclasses import dataclass

from crypto_research.diagnostics_v7 import mechanism_fingerprint, reject_repeated_mechanism

_ALLOWED_ACTIONS = (
    "veto_entry",
    "veto_increase",
    "scale_increase",
    "reliability_score",
    "risk_context",
    "event_risk_context",
)
_BLOCKED_PATTERNS = (
    r"\bgo\s+long\b",
    r"\bgo\s+short\b",
    r"\bbuy\s+(btc|eth|sol|xrp|doge|ada)\b",
    r"\bsell\s+(btc|eth|sol|xrp|doge|ada)\b",
    r"\bdirect\s+directional\s+alpha\b",
    r"\bflip\s+h12\b",
)


@dataclass(frozen=True)
class ResearchHypothesis:
    hypothesis_id: str
    target_error: str
    observation: str
    causal_inputs: tuple[str, ...]
    expected_mechanism: str
    single_change: str
    expected_effect: str
    cost_risk: str
    invalidation_condition: str
    required_test: str
    factor_family: str
    source_ids: tuple[str, ...]
    materially_new_evidence: bool


@dataclass(frozen=True)
class ExperimentManifest:
    hypothesis_id: str
    trial_phase: str
    causal_inputs: tuple[str, ...]
    train_window: tuple[str, str]
    evaluation_window: tuple[str, str]
    metrics: tuple[str, ...]
    cost_bps: tuple[float, ...]
    delay_minutes: tuple[int, ...]
    allowed_actions: tuple[str, ...]


def _contains_direct_direction(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _BLOCKED_PATTERNS)


def validate_hypothesis(
    hypothesis: ResearchHypothesis,
    *,
    blocked_fingerprints: set[str],
) -> ResearchHypothesis:
    for field_name in (
        "hypothesis_id",
        "target_error",
        "observation",
        "expected_mechanism",
        "single_change",
        "expected_effect",
        "cost_risk",
        "invalidation_condition",
        "required_test",
        "factor_family",
    ):
        if not str(getattr(hypothesis, field_name)).strip():
            raise ValueError(f"{field_name} must be non-empty")
    if not hypothesis.causal_inputs or not hypothesis.source_ids:
        raise ValueError("hypothesis requires causal inputs and source evidence")

    text = " ".join(
        (
            hypothesis.observation,
            hypothesis.expected_mechanism,
            hypothesis.single_change,
            hypothesis.expected_effect,
        )
    )
    if _contains_direct_direction(text):
        raise ValueError("direct direction proposal is forbidden")
    lowered_change = hypothesis.single_change.lower()
    if "leverage" in lowered_change or "execution mode" in lowered_change:
        raise ValueError("V7 factor hypotheses cannot change leverage or execution mode")

    fingerprint = mechanism_fingerprint(
        hypothesis.target_error,
        hypothesis.expected_mechanism,
        list(hypothesis.causal_inputs),
        hypothesis.single_change,
    )
    reject_repeated_mechanism(
        fingerprint,
        blocked_fingerprints,
        materially_new_evidence=hypothesis.materially_new_evidence,
    )
    return hypothesis


def build_experiment_manifest(
    hypothesis: ResearchHypothesis,
    *,
    train_window: tuple[str, str],
    evaluation_window: tuple[str, str],
) -> ExperimentManifest:
    return ExperimentManifest(
        hypothesis_id=hypothesis.hypothesis_id,
        trial_phase="escalation",
        causal_inputs=hypothesis.causal_inputs,
        train_window=train_window,
        evaluation_window=evaluation_window,
        metrics=("net_return", "sharpe", "max_drawdown", hypothesis.target_error),
        cost_bps=(10.0, 20.0),
        delay_minutes=(0, 60),
        allowed_actions=_ALLOWED_ACTIONS,
    )
