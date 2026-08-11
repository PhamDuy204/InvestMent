import json

import pandas as pd

from crypto_research.run_v7 import run_v7_first_line


def _inputs():
    times = pd.date_range("2026-01-01", periods=12, freq="12h", tz="UTC")
    decision_rows = []
    qh_rows = []
    for index, timestamp in enumerate(times):
        for symbol, side in (("A", 1.0), ("B", -1.0)):
            realized = 0.01 if index % 3 else -0.015
            score = 0.04 * side
            decision_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "target_weight": 0.2 * side,
                    "holding_return_label": realized * side,
                    "funding_sum_label": 0.0,
                    "effective_score": score,
                    "realized_net_contribution": realized * 0.2,
                    "fold": index // 4,
                }
            )
            qh_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "symbol": symbol,
                    "qh_order_imbalance": score * 5.0,
                    "qh_abs_order_imbalance": abs(score * 5.0),
                    "qh_trade_count": 5,
                }
            )
    decisions = pd.DataFrame(decision_rows)
    qh = pd.DataFrame(qh_rows)
    dispersion = pd.DataFrame(
        {
            "decision_timestamp": times,
            "dispersion_iqr": [0.01 + 0.001 * index for index in range(len(times))],
            "eligible_symbol_count": [2] * len(times),
        }
    )
    return decisions, qh, dispersion


def test_first_line_persists_attribution_failure_memory_and_do_not_repeat(tmp_path):
    decisions, qh, dispersion = _inputs()
    result = run_v7_first_line(decisions, qh, dispersion, artifact_root=tmp_path)
    assert result["promoted"] == []

    attribution = json.loads((tmp_path / "error_attribution.json").read_text())
    assert set(attribution["candidates"]) == {
        "H1_qh_conflict_veto",
        "H2_high_dispersion_gate",
        "H3_weak_edge_veto",
    }
    for payload in attribution["candidates"].values():
        assert "by_error" in payload
        assert "net_bps_effect" in payload

    ledger = pd.read_csv(tmp_path / "failure_ledger.csv.gz")
    assert len(ledger) == 3
    assert set(ledger["hypothesis"]) == set(attribution["candidates"])
    assert set(ledger["assumption_status"]) == {"not_supported"}
    assert ledger["failure_reason"].str.len().gt(0).all()

    blocked = json.loads((tmp_path / "do_not_repeat.json").read_text())
    assert len(blocked["fingerprints"]) == 3
    assert len(set(blocked["fingerprints"])) == 3
