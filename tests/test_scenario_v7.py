import json
from dataclasses import fields
from types import SimpleNamespace

import pandas as pd
import pytest

from crypto_research.scenario_v7 import (
    DisabledScenarioSimulator,
    MiroFishSidecarClient,
    ScenarioRequest,
    ScenarioResult,
    build_scenario_event_study,
)


def _request():
    return ScenarioRequest(
        event_id="e1",
        event_timestamp_utc="2026-01-01T00:00:00Z",
        event_text="unexpected funding dislocation",
        causal_context={"funding": 0.001},
        participant_roles=("market_maker", "leveraged_trader"),
    )


def _result(event_id="e1"):
    return ScenarioResult(
        event_id=event_id,
        consensus_strength=0.7,
        scenario_disagreement=0.3,
        tail_risk_bucket="high",
        liquidity_stress_bucket="medium",
        narrative_polarity=-0.2,
        confidence=0.6,
    )


def test_scenario_result_has_no_direct_trading_fields_and_validates_ranges():
    forbidden = {"side", "position", "buy", "sell", "long", "short"}
    assert not forbidden & {field.name.lower() for field in fields(ScenarioResult)}
    assert _result().source == "MIROFISH_OASIS_SIDECAR"
    with pytest.raises(ValueError, match="consensus_strength"):
        ScenarioResult("e", 1.1, 0.2, "low", "low", 0.0, 0.5)
    with pytest.raises(ValueError, match="narrative_polarity"):
        ScenarioResult("e", 0.5, 0.2, "low", "low", 2.0, 0.5)


def test_disabled_simulator_is_explicit_and_does_not_invent_result():
    disabled = DisabledScenarioSimulator()
    response = disabled.run(_request())
    assert response == {"status": "SCENARIO_SIMULATOR_NOT_CONFIGURED"}


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_sidecar_client_accepts_only_strict_scenario_schema():
    payload = {
        "event_id": "e1",
        "consensus_strength": 0.6,
        "scenario_disagreement": 0.4,
        "tail_risk_bucket": "high",
        "liquidity_stress_bucket": "medium",
        "narrative_polarity": -0.1,
        "confidence": 0.7,
        "source": "MIROFISH_OASIS_SIDECAR",
    }
    calls = []

    def opener(request, timeout):
        calls.append(SimpleNamespace(url=request.full_url, timeout=timeout, body=request.data))
        return _Response(payload)

    client = MiroFishSidecarClient("http://127.0.0.1:9999/simulate", opener=opener)
    result = client.run(_request())
    assert result.event_id == "e1"
    assert calls[0].url == "http://127.0.0.1:9999/simulate"
    assert calls[0].timeout == 30.0

    bad = {**payload, "side": "SHORT"}
    bad_client = MiroFishSidecarClient(
        "http://127.0.0.1:9999/simulate",
        opener=lambda request, timeout: _Response(bad),
    )
    with pytest.raises(ValueError, match="unexpected scenario fields"):
        bad_client.run(_request())


def _event_frames(count=12, timing_violation=False):
    ids = [f"e{index}" for index in range(count)]
    timestamps = pd.date_range("2025-01-01", periods=count, freq="7D", tz="UTC")
    cutoffs = timestamps - pd.Timedelta(minutes=1)
    if timing_violation and count:
        cutoffs = cutoffs.to_series(index=range(count))
        cutoffs.iloc[0] = timestamps[0] + pd.Timedelta(minutes=1)
        cutoffs = pd.DatetimeIndex(cutoffs)
    events = pd.DataFrame(
        {
            "event_id": ids,
            "event_timestamp_utc": timestamps,
            "data_cutoff_utc": cutoffs,
        }
    )
    scenario = pd.DataFrame(
        {
            "event_id": ids,
            "scenario_disagreement": [0.4] * count,
            "confidence": [0.7] * count,
        }
    )
    outcomes = pd.DataFrame(
        {
            "event_id": ids,
            "evaluation_fold": [index % 2 for index in range(count)],
            "baseline_net_bps": [0.0] * count,
            "scenario_context_net_bps": [1.0] * count,
        }
    )
    return events, scenario, outcomes


def test_scenario_event_study_requires_12_events_and_two_folds():
    events, scenario, outcomes = _event_frames(count=11)
    result = build_scenario_event_study(events, scenario, outcomes)
    assert result["status"] == "INSUFFICIENT_EVENT_EVIDENCE"
    assert result["distinct_event_count"] == 11


def test_scenario_event_study_enforces_causal_cutoff_and_positive_incremental_value():
    events, scenario, outcomes = _event_frames(count=12)
    result = build_scenario_event_study(events, scenario, outcomes)
    assert result["status"] == "ADMITTED_FOR_CHALLENGE"
    assert result["distinct_event_count"] == 12
    assert result["evaluation_fold_count"] == 2
    assert result["incremental_net_bps"] == pytest.approx(1.0)

    bad_events, scenario, outcomes = _event_frames(count=12, timing_violation=True)
    bad = build_scenario_event_study(bad_events, scenario, outcomes)
    assert bad["status"] == "NOT_ADMITTED_CAUSAL_TIMING_VIOLATION"
