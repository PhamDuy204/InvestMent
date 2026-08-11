import json

import pytest

from crypto_research.decision_diagnostics import V7_CAUSAL_COLUMNS, V7_LABEL_COLUMNS
from crypto_research.diagnostics_v7 import (
    build_failure_record,
    load_do_not_repeat,
    mechanism_fingerprint,
    reject_repeated_mechanism,
    write_do_not_repeat,
)


def test_mechanism_fingerprint_ignores_spacing_case_and_input_order():
    a = mechanism_fingerprint(
        "WRONG_SIDE",
        "QH conflict veto",
        ["qh_order_imbalance", "h12_score"],
        "veto_increase",
    )
    b = mechanism_fingerprint(
        "wrong_side",
        "  qh   conflict   veto ",
        ["h12_score", "qh_order_imbalance"],
        "VETO_INCREASE",
    )
    assert a == b


def test_repeated_failed_mechanism_requires_materially_new_evidence():
    with pytest.raises(ValueError, match="do-not-repeat"):
        reject_repeated_mechanism("abc", {"abc"})
    reject_repeated_mechanism("abc", {"abc"}, materially_new_evidence=True)


def test_failure_record_contains_required_economic_fields():
    record = build_failure_record(
        trial_number=858,
        hypothesis="H1_qh_conflict_veto",
        target_error="WRONG_SIDE",
        expected_mechanism="QH conflict veto",
        causal_inputs=["qh_order_imbalance", "h12_score"],
        action="veto_increase",
        actual_error_delta=3,
        net_effect_bps=-4.2,
        turnover_effect=-0.1,
        drawdown_effect=0.002,
        damaged_regime="low_liquidity",
        helped_regime="high_activity",
        assumption_status="not_supported",
        failure_reason="wrong-side count increased",
        next_allowed_question="does conflict matter only under high dispersion?",
        timestamp_utc="2026-08-11T04:00:00Z",
    )
    required = {
        "target_error",
        "expected_mechanism",
        "actual_error_delta",
        "net_effect_bps",
        "turnover_effect",
        "drawdown_effect",
        "damaged_regime",
        "helped_regime",
        "assumption_status",
        "failure_reason",
        "do_not_repeat_fingerprint",
        "next_allowed_question",
    }
    assert required.issubset(record)


def test_do_not_repeat_round_trip(tmp_path):
    path = tmp_path / "do_not_repeat.json"
    write_do_not_repeat(
        [
            {"do_not_repeat_fingerprint": "b", "expected_mechanism": "second"},
            {"do_not_repeat_fingerprint": "a", "expected_mechanism": "first"},
            {"do_not_repeat_fingerprint": "a", "expected_mechanism": "first duplicate"},
        ],
        path,
    )
    payload = json.loads(path.read_text())
    assert payload["fingerprints"] == ["a", "b"]
    assert load_do_not_repeat(path) == {"a", "b"}


def test_v7_oracle_and_realized_fields_are_label_only():
    assert not set(V7_CAUSAL_COLUMNS) & set(V7_LABEL_COLUMNS)
    for name in ("realized_return", "oracle_direction", "WRONG_SIDE"):
        assert name in V7_LABEL_COLUMNS
        assert name not in V7_CAUSAL_COLUMNS
    for name in (
        "qh_order_imbalance",
        "qh_abs_order_imbalance",
        "dispersion_iqr",
        "qh_abs_threshold",
        "dispersion_threshold",
        "weak_score_threshold",
    ):
        assert name in V7_CAUSAL_COLUMNS
