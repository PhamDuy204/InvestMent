from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_COLUMNS = ["trial_number", "trial_id", "stage", "hypothesis", "status", "config_hash", "metrics_json", "timestamp_utc"]


class TrialRegistry:
    def __init__(self, path: str | Path, *, prior_count: int = 779):
        if prior_count < 0:
            raise ValueError("prior_count must be non-negative")
        self.path = Path(path)
        self.prior_count = int(prior_count)
        if self.path.exists():
            frame = pd.read_csv(self.path)
            self.rows = frame.to_dict("records")
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
    ) -> dict[str, object]:
        payload = json.dumps(config or {}, sort_keys=True, separators=(",", ":"), default=str)
        config_hash = hashlib.sha256(payload.encode()).hexdigest()
        trial_number = self.prior_count + len(self.rows) + 1
        trial_id = f"v6-{trial_number:04d}-{config_hash[:10]}"
        row = {
            "trial_number": trial_number,
            "trial_id": trial_id,
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
