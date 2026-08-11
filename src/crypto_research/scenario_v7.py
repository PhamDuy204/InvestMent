from __future__ import annotations

import json
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable

import pandas as pd

_BUCKETS = {"low", "medium", "high", "extreme"}
_SCENARIO_RESULT_FIELDS = {
    "event_id",
    "consensus_strength",
    "scenario_disagreement",
    "tail_risk_bucket",
    "liquidity_stress_bucket",
    "narrative_polarity",
    "confidence",
    "source",
}


@dataclass(frozen=True)
class ScenarioRequest:
    event_id: str
    event_timestamp_utc: str
    event_text: str
    causal_context: dict[str, Any]
    participant_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.event_text.strip():
            raise ValueError("event_id and event_text must be non-empty")
        timestamp = pd.Timestamp(self.event_timestamp_utc)
        if timestamp.tzinfo is None:
            raise ValueError("event_timestamp_utc must be timezone-aware")


@dataclass(frozen=True)
class ScenarioResult:
    event_id: str
    consensus_strength: float
    scenario_disagreement: float
    tail_risk_bucket: str
    liquidity_stress_bucket: str
    narrative_polarity: float
    confidence: float
    source: str = "MIROFISH_OASIS_SIDECAR"

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        for field_name in ("consensus_strength", "scenario_disagreement", "confidence"):
            value = float(getattr(self, field_name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be in [0, 1]")
        if not -1.0 <= float(self.narrative_polarity) <= 1.0:
            raise ValueError("narrative_polarity must be in [-1, 1]")
        if self.tail_risk_bucket not in _BUCKETS:
            raise ValueError("invalid tail_risk_bucket")
        if self.liquidity_stress_bucket not in _BUCKETS:
            raise ValueError("invalid liquidity_stress_bucket")
        if self.source != "MIROFISH_OASIS_SIDECAR":
            raise ValueError("unexpected scenario source")


class DisabledScenarioSimulator:
    def run(self, request: ScenarioRequest) -> dict[str, str]:
        del request
        return {"status": "SCENARIO_SIMULATOR_NOT_CONFIGURED"}


class MiroFishSidecarClient:
    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 30.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not endpoint.strip():
            raise ValueError("endpoint must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.endpoint = endpoint
        self.timeout_seconds = float(timeout_seconds)
        self.opener = opener or urllib.request.urlopen

    def run(self, request: ScenarioRequest) -> ScenarioResult:
        body = asdict(request)
        body["participant_roles"] = list(request.participant_roles)
        encoded = json.dumps(body, sort_keys=True, default=str).encode()
        http_request = urllib.request.Request(
            self.endpoint,
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(http_request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode())
        if set(payload) != _SCENARIO_RESULT_FIELDS:
            extra = sorted(set(payload).difference(_SCENARIO_RESULT_FIELDS))
            missing = sorted(_SCENARIO_RESULT_FIELDS.difference(payload))
            raise ValueError(f"unexpected scenario fields extra={extra} missing={missing}")
        return ScenarioResult(**payload)


def build_scenario_event_study(
    events: pd.DataFrame,
    scenario_results: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> dict[str, object]:
    required_events = {"event_id", "event_timestamp_utc", "data_cutoff_utc"}
    required_scenario = {"event_id", "scenario_disagreement", "confidence"}
    required_outcomes = {
        "event_id",
        "evaluation_fold",
        "baseline_net_bps",
        "scenario_context_net_bps",
    }
    if missing := required_events.difference(events.columns):
        raise ValueError(f"events missing columns: {sorted(missing)}")
    if missing := required_scenario.difference(scenario_results.columns):
        raise ValueError(f"scenario_results missing columns: {sorted(missing)}")
    if missing := required_outcomes.difference(outcomes.columns):
        raise ValueError(f"outcomes missing columns: {sorted(missing)}")

    event_frame = events.copy()
    event_frame["event_timestamp_utc"] = pd.to_datetime(event_frame["event_timestamp_utc"], utc=True)
    event_frame["data_cutoff_utc"] = pd.to_datetime(event_frame["data_cutoff_utc"], utc=True)
    if event_frame["event_id"].duplicated().any():
        raise ValueError("events must have unique event_id")
    causal_ok = event_frame["data_cutoff_utc"].le(event_frame["event_timestamp_utc"])
    if not bool(causal_ok.all()):
        return {
            "status": "NOT_ADMITTED_CAUSAL_TIMING_VIOLATION",
            "distinct_event_count": int(event_frame["event_id"].nunique()),
            "causal_timing_violation_count": int((~causal_ok).sum()),
        }

    merged = event_frame.merge(
        scenario_results,
        on="event_id",
        how="inner",
        validate="one_to_one",
    ).merge(
        outcomes,
        on="event_id",
        how="inner",
        validate="one_to_one",
    )
    distinct_event_count = int(merged["event_id"].nunique())
    evaluation_fold_count = int(merged["evaluation_fold"].nunique())
    if distinct_event_count < 12 or evaluation_fold_count < 2:
        return {
            "status": "INSUFFICIENT_EVENT_EVIDENCE",
            "distinct_event_count": distinct_event_count,
            "evaluation_fold_count": evaluation_fold_count,
            "minimum_distinct_events": 12,
            "minimum_evaluation_folds": 2,
        }

    merged["incremental_net_bps"] = (
        pd.to_numeric(merged["scenario_context_net_bps"], errors="coerce")
        - pd.to_numeric(merged["baseline_net_bps"], errors="coerce")
    )
    incremental = float(merged["incremental_net_bps"].mean())
    fold_means = merged.groupby("evaluation_fold")["incremental_net_bps"].mean()
    positive_fold_count = int((fold_means > 0.0).sum())
    admitted = incremental > 0.0 and positive_fold_count >= 2
    return {
        "status": (
            "ADMITTED_FOR_CHALLENGE"
            if admitted
            else "NOT_ADMITTED_NONPOSITIVE_OR_UNSTABLE_INCREMENTAL_VALUE"
        ),
        "distinct_event_count": distinct_event_count,
        "evaluation_fold_count": evaluation_fold_count,
        "positive_fold_count": positive_fold_count,
        "incremental_net_bps": incremental,
        "mean_scenario_disagreement": float(
            pd.to_numeric(merged["scenario_disagreement"], errors="coerce").mean()
        ),
        "mean_confidence": float(pd.to_numeric(merged["confidence"], errors="coerce").mean()),
    }
