from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_COLUMNS = [
    "trial_number",
    "trial_id",
    "phase",
    "stage",
    "hypothesis",
    "status",
    "config_hash",
    "metrics_json",
    "timestamp_utc",
]


class V7TrialRegistry:
    def __init__(
        self,
        path: str | Path,
        *,
        prior_count: int = 857,
        first_line_cap: int = 24,
        total_cap: int = 60,
    ) -> None:
        if prior_count != 857:
            raise ValueError("V7 prior_count must remain 857")
        if first_line_cap <= 0 or total_cap < first_line_cap:
            raise ValueError("invalid V7 trial budgets")
        self.path = Path(path)
        self.prior_count = int(prior_count)
        self.first_line_cap = int(first_line_cap)
        self.total_cap = int(total_cap)
        if self.path.exists():
            frame = pd.read_csv(self.path)
            missing = set(_COLUMNS).difference(frame.columns)
            if missing:
                raise ValueError(f"registry missing columns: {sorted(missing)}")
            self.rows = frame[_COLUMNS].to_dict("records")
        else:
            self.rows: list[dict[str, object]] = []

    @property
    def total_count(self) -> int:
        return self.prior_count + len(self.rows)

    def record(
        self,
        stage: str,
        hypothesis: str,
        status: str,
        *,
        config: dict[str, object] | None = None,
        metrics: dict[str, object] | None = None,
        phase: str = "first_line",
    ) -> dict[str, object]:
        if len(self.rows) >= self.total_cap:
            raise RuntimeError("V7 total trial budget exhausted")
        if phase == "first_line":
            first_line_count = sum(str(row.get("phase")) == "first_line" for row in self.rows)
            if first_line_count >= self.first_line_cap:
                raise RuntimeError("V7 first-line trial budget exhausted")
        payload = json.dumps(config or {}, sort_keys=True, separators=(",", ":"), default=str)
        config_hash = hashlib.sha256(payload.encode()).hexdigest()
        trial_number = self.prior_count + len(self.rows) + 1
        row = {
            "trial_number": trial_number,
            "trial_id": f"v7-{trial_number:04d}-{config_hash[:10]}",
            "phase": str(phase),
            "stage": str(stage),
            "hypothesis": str(hypothesis),
            "status": str(status),
            "config_hash": config_hash,
            "metrics_json": json.dumps(metrics or {}, sort_keys=True, default=str),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        self.rows.append(row)
        return row

    def to_csv(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.rows, columns=_COLUMNS).to_csv(self.path, index=False)
        return self.path
