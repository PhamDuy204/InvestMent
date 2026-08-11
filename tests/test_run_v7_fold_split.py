import pandas as pd

from crypto_research.run_v7 import split_selection_evaluation


def test_split_selection_evaluation_preserves_all_outer_folds() -> None:
    rows = []
    for fold in range(3):
        times = pd.date_range(f"2026-0{fold + 1}-01", periods=10, freq="12h", tz="UTC")
        for timestamp in times:
            rows.append({"decision_timestamp": timestamp, "symbol": "BTCUSDT", "fold": fold})
    frame = pd.DataFrame(rows)

    selection, evaluation = split_selection_evaluation(frame, selection_fraction=0.70)

    assert set(selection["fold"]) == {0, 1, 2}
    assert set(evaluation["fold"]) == {0, 1, 2}
    for fold in (0, 1, 2):
        train_fold = selection.loc[selection["fold"] == fold]
        eval_fold = evaluation.loc[evaluation["fold"] == fold]
        assert train_fold["decision_timestamp"].max() < eval_fold["decision_timestamp"].min()
        assert train_fold["decision_timestamp"].nunique() == 7
        assert eval_fold["decision_timestamp"].nunique() == 3
