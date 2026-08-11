from __future__ import annotations

from pathlib import Path

PATH = Path("src/crypto_research/run_v7.py")


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one methodology sync anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    replay_anchor = '''    if round_trip_cost_bps < 0:\n        raise ValueError("round_trip_cost_bps must be non-negative")\n\n    work = decision_log.copy()\n'''
    replay_replacement = '''    if round_trip_cost_bps < 0:\n        raise ValueError("round_trip_cost_bps must be non-negative")\n\n    if (\n        "fold" in decision_log.columns\n        and decision_log["fold"].notna().all()\n        and decision_log["fold"].nunique() > 1\n    ):\n        ordered = decision_log.copy()\n        ordered["decision_timestamp"] = pd.to_datetime(ordered["decision_timestamp"], utc=True)\n        ordered = ordered.sort_values(["decision_timestamp", "symbol"])\n        period_parts: list[pd.DataFrame] = []\n        decision_parts: list[pd.DataFrame] = []\n        for _, part in ordered.groupby("fold", sort=False):\n            periods, decisions, _ = replay_v7_reliability(\n                part,\n                config,\n                round_trip_cost_bps=round_trip_cost_bps,\n            )\n            period_parts.append(periods)\n            decision_parts.append(decisions)\n        combined_periods = pd.concat(period_parts, ignore_index=True)\n        combined_decisions = pd.concat(decision_parts, ignore_index=True)\n        return combined_periods, combined_decisions, stateful_summary(combined_periods)\n\n    work = decision_log.copy()\n'''
    text = replace_once(text, replay_anchor, replay_replacement)

    split_anchor = '''    work = decision_log.copy()\n    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)\n    times = pd.Index(sorted(work["decision_timestamp"].dropna().unique()))\n'''
    split_replacement = '''    work = decision_log.copy()\n    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)\n    if (\n        "fold" in work.columns\n        and work["fold"].notna().all()\n        and work["fold"].nunique() > 1\n    ):\n        selection_parts: list[pd.DataFrame] = []\n        evaluation_parts: list[pd.DataFrame] = []\n        for _, part in work.groupby("fold", sort=False):\n            times = pd.Index(sorted(part["decision_timestamp"].dropna().unique()))\n            if len(times) < 4:\n                raise ValueError("each fold requires at least four decision timestamps")\n            split = max(1, min(len(times) - 1, int(len(times) * selection_fraction)))\n            cutoff = times[split - 1]\n            selection_parts.append(part.loc[part["decision_timestamp"] <= cutoff].copy())\n            evaluation_parts.append(part.loc[part["decision_timestamp"] > cutoff].copy())\n        return (\n            pd.concat(selection_parts).sort_values(["decision_timestamp", "symbol"]),\n            pd.concat(evaluation_parts).sort_values(["decision_timestamp", "symbol"]),\n        )\n\n    times = pd.Index(sorted(work["decision_timestamp"].dropna().unique()))\n'''
    text = replace_once(text, split_anchor, split_replacement)

    first_line_anchor = '''    delay_decision_log: pd.DataFrame | None = None,\n) -> dict[str, Any]:\n    root = Path(artifact_root)\n'''
    first_line_replacement = '''    delay_decision_log: pd.DataFrame | None = None,\n) -> dict[str, Any]:\n    if (\n        "fold" in decision_log.columns\n        and decision_log["fold"].notna().all()\n        and decision_log["fold"].nunique() > 1\n    ):\n        from crypto_research.run_v7_foldwise import run_v7_first_line_foldwise\n\n        return run_v7_first_line_foldwise(\n            decision_log,\n            qh_features,\n            dispersion,\n            artifact_root=artifact_root,\n            prior_trials=prior_trials,\n            round_trip_cost_bps=round_trip_cost_bps,\n            selection_fraction=selection_fraction,\n            delay_decision_log=delay_decision_log,\n        )\n\n    root = Path(artifact_root)\n'''
    text = replace_once(text, first_line_anchor, first_line_replacement)

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
