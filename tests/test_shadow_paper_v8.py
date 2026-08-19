from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from crypto_research.shadow_paper_v8 import ShadowPaperEngine, SimulatedBroker


def test_shadow_engine_routes_decision_to_simulated_broker_only(tmp_path) -> None:
    engine = ShadowPaperEngine(
        broker=SimulatedBroker(fee_bps=4.0),
        journal_path=tmp_path / "shadow.jsonl",
    )
    decision_time = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

    row = engine.record_decision(
        timestamp=decision_time,
        candidate_hash="candidate-dev",
        candidate_frozen=False,
        freeze_timestamp=None,
        signal=0.7,
        target_exposure=0.25,
        target_notional=100.0,
        side="buy",
        book={"bids": [[99.0, 2.0]], "asks": [[100.0, 2.0]]},
        funding_rate=0.0001,
    )

    assert row["record_type"] == "DECISION"
    assert row["execution_type"] == "SIMULATED_FILL_ONLY"
    assert row["evidence_class"] == "ENGINEERING_ONLY"
    assert row["simulated_fill"]["filled_notional"] == 100.0
    assert row["simulated_fill"]["unfilled_notional"] == 0.0


def test_shadow_engine_only_marks_post_freeze_decisions_a1_eligible(tmp_path) -> None:
    engine = ShadowPaperEngine(
        broker=SimulatedBroker(),
        journal_path=tmp_path / "shadow.jsonl",
    )
    freeze = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
    book = {"bids": [[99.0, 2.0]], "asks": [[100.0, 2.0]]}

    eligible = engine.record_decision(
        timestamp=freeze + timedelta(hours=1),
        candidate_hash="frozen-hash",
        candidate_frozen=True,
        freeze_timestamp=freeze,
        signal=-0.5,
        target_exposure=-0.2,
        target_notional=50.0,
        side="sell",
        book=book,
    )
    assert eligible["evidence_class"] == "FORWARD_A1_ELIGIBLE"

    with pytest.raises(ValueError, match="freeze_timestamp"):
        engine.record_decision(
            timestamp=freeze - timedelta(seconds=1),
            candidate_hash="frozen-hash",
            candidate_frozen=True,
            freeze_timestamp=freeze,
            signal=-0.5,
            target_exposure=-0.2,
            target_notional=50.0,
            side="sell",
            book=book,
        )


def test_shadow_outcome_is_append_only_and_cannot_be_added_before_horizon(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    engine = ShadowPaperEngine(broker=SimulatedBroker(), journal_path=path)
    decision = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    row = engine.record_decision(
        timestamp=decision,
        candidate_hash="dev",
        candidate_frozen=False,
        freeze_timestamp=None,
        signal=0.2,
        target_exposure=0.1,
        target_notional=20.0,
        side="buy",
        book={"bids": [[99.0, 2.0]], "asks": [[100.0, 2.0]]},
    )

    with pytest.raises(ValueError, match="horizon"):
        engine.append_outcome(
            decision_id=row["decision_id"],
            evaluated_at=decision + timedelta(hours=1),
            horizon_hours=12,
            realized_future_return=0.01,
        )

    engine.append_outcome(
        decision_id=row["decision_id"],
        evaluated_at=decision + timedelta(hours=13),
        horizon_hours=12,
        realized_future_return=0.01,
    )
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert records[0]["record_type"] == "DECISION"
    assert records[1]["record_type"] == "OUTCOME"
    assert records[1]["paper_pnl_return"] is not None
