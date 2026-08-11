import pandas as pd

from crypto_research.run_v7 import run_v7_first_line


def test_first_line_fits_gate_thresholds_separately_inside_each_outer_fold(tmp_path) -> None:
    rows = []
    qh_rows = []
    dispersion_rows = []
    for fold, base_dispersion in ((0, 0.01), (1, 0.10), (2, 1.00)):
        times = pd.date_range(f"2026-0{fold + 1}-01", periods=10, freq="12h", tz="UTC")
        for index, timestamp in enumerate(times):
            dispersion_rows.append(
                {
                    "decision_timestamp": timestamp,
                    "dispersion_iqr": base_dispersion + index * base_dispersion * 0.01,
                    "eligible_symbol_count": 2,
                }
            )
            for symbol, side in (("A", 1.0), ("B", -1.0)):
                rows.append(
                    {
                        "decision_timestamp": timestamp,
                        "symbol": symbol,
                        "target_weight": 0.2 * side,
                        "holding_return_label": 0.01 * side,
                        "funding_sum_label": 0.0,
                        "effective_score": (0.01 + 0.001 * index) * side,
                        "realized_net_contribution": 0.002,
                        "fold": fold,
                    }
                )
                qh_rows.append(
                    {
                        "decision_timestamp": timestamp,
                        "symbol": symbol,
                        "qh_order_imbalance": 0.1 * side,
                        "qh_abs_order_imbalance": 0.1,
                        "qh_trade_count": 5,
                    }
                )

    result = run_v7_first_line(
        pd.DataFrame(rows),
        pd.DataFrame(qh_rows),
        pd.DataFrame(dispersion_rows),
        artifact_root=tmp_path,
    )

    per_fold = result["fitted_gate_config"]["per_fold"]
    thresholds = [per_fold[str(fold)]["dispersion_threshold"] for fold in (0, 1, 2)]
    assert thresholds[0] < thresholds[1] < thresholds[2]
    for fold in (0, 1, 2):
        assert per_fold[str(fold)]["qh_abs_threshold"] == 0.1
