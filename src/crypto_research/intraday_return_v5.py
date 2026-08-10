from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_research.burst_model_v5 import BURST_FEATURES, economic_event_metrics, non_overlapping_mask


def _load(table_root: Path) -> pd.DataFrame:
    cols = ["timestamp", "symbol", *BURST_FEATURES, "tradable_return_15m", "tradable_return_60m"]
    parts = [pd.read_pickle(path).loc[:, cols] for path in sorted(table_root.glob("*.pkl"))]
    if not parts:
        raise ValueError("no burst tables")
    data = pd.concat(parts, ignore_index=True).replace([np.inf, -np.inf], np.nan)
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    return data.dropna(subset=BURST_FEATURES)


def _fit_ridge(train: pd.DataFrame, target: str, random_state: int):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    fit = train.dropna(subset=[target])
    if len(fit) > 800_000:
        fit = fit.sample(800_000, random_state=random_state)
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(fit[BURST_FEATURES], fit[target])
    return model


def _evaluate(scored: pd.DataFrame, *, horizon: int, threshold: float, cost_bps: float):
    target = f"tradable_return_{horizon}m"
    pred = f"pred_{horizon}m"
    work = scored.dropna(subset=[target, pred]).copy()
    work["eligible"] = work[pred].abs().ge(threshold)
    mask = non_overlapping_mask(work[["timestamp", "symbol", "eligible"]], horizon_minutes=horizon)
    events = work.loc[mask].copy()
    events["gross_signal_return"] = np.sign(events[pred]) * events[target]
    return events, economic_event_metrics(events["gross_signal_return"], round_trip_cost_bps=cost_bps)


def run_intraday_return_research(*, table_root: str | Path, artifact_root: str | Path, cost_bps: float = 10.0, random_state: int = 42) -> dict[str, object]:
    data = _load(Path(table_root))
    train = data.loc[data["timestamp"] < pd.Timestamp("2026-01-01", tz="UTC")].copy()
    validation = data.loc[(data["timestamp"] >= pd.Timestamp("2026-01-01", tz="UTC")) & (data["timestamp"] < pd.Timestamp("2026-05-01", tz="UTC"))].copy()
    test = data.loc[data["timestamp"] >= pd.Timestamp("2026-05-01", tz="UTC")].copy()
    output = {"rows": {"train": len(train), "validation": len(validation), "test": len(test)}, "horizons": {}, "trial_count": 0}
    artifact_root = Path(artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    for horizon in (15, 60):
        target = f"tradable_return_{horizon}m"
        pred = f"pred_{horizon}m"
        model = _fit_ridge(train, target, random_state)
        validation[pred] = model.predict(validation[BURST_FEATURES])
        test[pred] = model.predict(test[BURST_FEATURES])
        val_valid = validation.dropna(subset=[target, pred])
        test_valid = test.dropna(subset=[target, pred])
        trials = []
        for threshold in (0.0010, 0.0015, 0.0020, 0.0030):
            _, metrics = _evaluate(validation, horizon=horizon, threshold=threshold, cost_bps=cost_bps)
            trials.append({"threshold": threshold, "metrics": metrics})
        output["trial_count"] += len(trials)
        eligible = [row for row in trials if row["metrics"]["count"] >= 200]
        selected = max(eligible, key=lambda row: (row["metrics"]["mean_net_return"], row["metrics"]["profit_factor"] or 0.0)) if eligible else None
        test_metrics = economic_event_metrics(pd.Series(dtype=float), round_trip_cost_bps=cost_bps)
        if selected:
            test_events, test_metrics = _evaluate(test, horizon=horizon, threshold=selected["threshold"], cost_bps=cost_bps)
            test_events.to_csv(artifact_root / f"events_{horizon}m.csv.gz", index=False, compression="gzip")
        output["horizons"][str(horizon)] = {"validation_correlation": float(np.corrcoef(val_valid[target], val_valid[pred])[0, 1]), "test_correlation": float(np.corrcoef(test_valid[target], test_valid[pred])[0, 1]), "threshold_trials": trials, "selected": selected, "test_metrics": test_metrics}
    (artifact_root / "intraday_return_results.json").write_text(json.dumps(output, indent=2, default=str))
    return output
