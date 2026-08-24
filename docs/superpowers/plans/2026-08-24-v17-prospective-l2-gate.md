# V17 Prospective L2 Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce the frozen V17/V32 DEVELOPMENT coverage rules with a deterministic metadata-only, fail-closed gate that cannot open outcomes or mutate recorder/trial/paper state.

**Architecture:** A pinned config supplies the immutable 21-symbol universe and strict nine-field metadata projection missing from the V32 boundary. A new pure gate module verifies finalized parquet sidecars, reads only projected metadata, computes hourly coverage/common gaps, returns one explicit `GateStatus`, hashes the complete audit, and builds weakness events. A thin CLI performs read-only input I/O and writes only outside the recorder root.

**Tech Stack:** Python 3.11, pandas/pyarrow already installed, standard-library JSON/hash/path/time APIs, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-paper-readiness-and-multi-market-design.md`

**Depends on:** `docs/superpowers/plans/2026-08-24-shared-strict-provenance-foundation.md` completed and green.

## Global Constraints

- Do not modify V32 history, `l2_shadow_v8.py`, either recorder, recorder data, `point_in_time_v8.py`, paper runtime, trial registry, candidate state, or outcome data.
- Read only `event_time`, `available_at`, `captured_at`, `source`, `source_id`, `symbol`, `update_id`, `data_version`, and opaque row `checksum`.
- Verify finalized `*.parquet.sha256` sidecars before projected parsing; never open `.pending.jsonl` as evidence.
- DEVELOPMENT is `[2026-08-24T06:00:00Z, 2026-08-31T06:00:00Z)`, exactly 168 hourly intervals.
- Each hour-end decision needs usable L2 for at least 20/21 symbols; every symbol needs at least 160/168 decisions.
- A common no-valid-row gap strictly greater than 15 minutes returns `RESET_REQUIRED`; exactly 15 minutes does not.
- `DEVELOPMENT_ELIGIBLE` cannot occur before the end boundary and never starts diagnostics, freezes candidates, consumes trial 871, or changes paper readiness.
- Invalid immutable input makes the epoch unusable; only byte-identical transient I/O input may be retried in the same epoch.
- Every result hard-codes `outcomes_opened=false`, `trial_871_authorized=false`, `trial_871_consumed=false`, `candidate_frozen=false`, `READY_TO_START_PAPER=false`, `A1=NOT_STARTED`, and `LIVE_NOT_AUTHORIZED`.
- No new dependency.
- Use the repo-local environment bootstrapped by the foundation plan; every fresh agent runs `source .venv/bin/activate` before task commands.

---

### Task 1: Pin the exact gate configuration and universe

**Files:**
- Create: `configs/v17_prospective_gate_v1.json`
- Create: `configs/v17_prospective_gate_v1.json.sha256`
- Create: `src/crypto_research/prospective_gate_v17.py`
- Create: `tests/test_prospective_gate_v17.py`

**Interfaces:**
- Consumes: approved V32 boundary and shared `canonical_sha256`/`canonical_utc`.
- Produces: immutable `GateConfig` and `load_gate_config(path, expected_hash) -> GateConfig`.

- [ ] **Step 1: Create the exact pinned config**

```json
{
  "schema_version": "v17-prospective-gate-config-1",
  "epoch_id": "v32-forward-l2-20260824T060000Z",
  "source_v32_git_sha": "5ce712bfc5b05007abe40046aef8abc98be8f1c4",
  "boundary_path": "paper_readiness_versions/version_32/10_forward_l2_prospective_boundary.json",
  "boundary_file_sha256": "019b997e99124ceda93a7bedaa9cb91d9651d820ece160cbfbbb918b60b83690",
  "boundary_canonical_sha256": "2becbac8bb672c1b910830c0855e244658e1be1387d141d6d838c8773a12b5a3",
  "development_start": "2026-08-24T06:00:00.000000Z",
  "development_end": "2026-08-31T06:00:00.000000Z",
  "decision_cadence_seconds": 3600,
  "maximum_common_gap_seconds": 900,
  "minimum_symbols_per_hour": 20,
  "minimum_hours_per_symbol": 160,
  "recorder_schema_version": "v8-l2-snapshot-1",
  "strict_l2_fields": [
    "event_time",
    "available_at",
    "captured_at",
    "source",
    "source_id",
    "symbol",
    "update_id",
    "data_version",
    "checksum"
  ],
  "expected_symbols": [
    "1000PEPE/USDT:USDT",
    "1000SHIB/USDT:USDT",
    "AAVE/USDT:USDT",
    "ADA/USDT:USDT",
    "AVAX/USDT:USDT",
    "BNB/USDT:USDT",
    "BTC/USDT:USDT",
    "DOGE/USDT:USDT",
    "DOT/USDT:USDT",
    "ETH/USDT:USDT",
    "FIL/USDT:USDT",
    "LINK/USDT:USDT",
    "LTC/USDT:USDT",
    "NEAR/USDT:USDT",
    "SOL/USDT:USDT",
    "SUI/USDT:USDT",
    "UNI/USDT:USDT",
    "WLD/USDT:USDT",
    "XLM/USDT:USDT",
    "XRP/USDT:USDT",
    "ZEC/USDT:USDT"
  ],
  "outcomes_opened": false,
  "trial_871_authorized": false,
  "trial_871_consumed": false,
  "candidate_frozen": false,
  "ready_to_start_paper": false,
  "a1": "NOT_STARTED",
  "live_authorization": "LIVE_NOT_AUTHORIZED"
}
```

- [ ] **Step 2: Generate the canonical config sidecar**

Run:

```bash
python - <<'PY' > configs/v17_prospective_gate_v1.json.sha256
import json
from pathlib import Path
from crypto_research.canonical_json import canonical_sha256

path = Path("configs/v17_prospective_gate_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))
print(canonical_sha256("forward-l2-gate-config-v1", payload))
PY
```

Expected: one lowercase 64-character SHA-256 plus newline.

- [ ] **Step 3: Write failing config tests**

```python
import json
from pathlib import Path

import pytest

from crypto_research.canonical_json import canonical_sha256
from crypto_research.prospective_gate_v17 import GateConfig, load_gate_config


CONFIG = Path("configs/v17_prospective_gate_v1.json")
CONFIG_HASH = Path("configs/v17_prospective_gate_v1.json.sha256").read_text().strip()


def test_gate_config_pins_exact_v17_universe_and_invariants() -> None:
    config = load_gate_config(CONFIG, expected_hash=CONFIG_HASH)

    assert isinstance(config, GateConfig)
    assert len(config.expected_symbols) == 21
    assert tuple(sorted(config.expected_symbols)) == config.expected_symbols
    assert config.minimum_symbols_per_hour == 20
    assert config.minimum_hours_per_symbol == 160
    assert config.decision_cadence_seconds == 3600
    assert config.maximum_common_gap_seconds == 900
    assert config.outcomes_opened is False
    assert config.trial_871_authorized is False
    assert config.trial_871_consumed is False
    assert config.candidate_frozen is False
    assert config.ready_to_start_paper is False
    assert config.a1 == "NOT_STARTED"
    assert config.live_authorization == "LIVE_NOT_AUTHORIZED"


def test_gate_config_hash_or_symbol_mutation_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text())
    payload["expected_symbols"] = payload["expected_symbols"][:-1]
    changed = tmp_path / "gate.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="config hash"):
        load_gate_config(changed, expected_hash=CONFIG_HASH)


def test_gate_config_rejects_semantic_mutation_even_with_recomputed_hash(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text())
    payload["minimum_symbols_per_hour"] = 19
    changed = tmp_path / "gate.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    changed_hash = canonical_sha256("forward-l2-gate-config-v1", payload)

    with pytest.raises(ValueError, match="threshold invariant"):
        load_gate_config(changed, expected_hash=changed_hash)
```

- [ ] **Step 4: Run the focused test and verify failure**

Run:

```bash
python -m pytest -q tests/test_prospective_gate_v17.py
```

Expected: import fails because `prospective_gate_v17.py` does not exist.

- [ ] **Step 5: Implement the config contract**

```python
"""Metadata-only prospective gate for the frozen V17/V32 L2 epoch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from crypto_research.canonical_json import canonical_sha256, canonical_utc

GATE_CONFIG_DOMAIN = "forward-l2-gate-config-v1"
GATE_RESULT_DOMAIN = "forward-l2-gate-v1"
STRICT_L2_FIELDS = (
    "event_time",
    "available_at",
    "captured_at",
    "source",
    "source_id",
    "symbol",
    "update_id",
    "data_version",
    "checksum",
)


@dataclass(frozen=True)
class GateConfig:
    schema_version: str
    epoch_id: str
    source_v32_git_sha: str
    boundary_path: str
    boundary_file_sha256: str
    boundary_canonical_sha256: str
    development_start: datetime
    development_end: datetime
    decision_cadence_seconds: int
    maximum_common_gap_seconds: int
    minimum_symbols_per_hour: int
    minimum_hours_per_symbol: int
    recorder_schema_version: str
    strict_l2_fields: tuple[str, ...]
    expected_symbols: tuple[str, ...]
    outcomes_opened: bool
    trial_871_authorized: bool
    trial_871_consumed: bool
    candidate_frozen: bool
    ready_to_start_paper: bool
    a1: str
    live_authorization: str


def load_gate_config(path: str | Path, *, expected_hash: str) -> GateConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    actual = canonical_sha256(GATE_CONFIG_DOMAIN, payload)
    if actual != expected_hash:
        raise ValueError("gate config hash mismatch")
    symbols = tuple(payload["expected_symbols"])
    fields = tuple(payload["strict_l2_fields"])
    if len(symbols) != 21 or symbols != tuple(sorted(set(symbols))):
        raise ValueError("gate config must pin 21 unique sorted symbols")
    if fields != STRICT_L2_FIELDS:
        raise ValueError("gate config strict field projection mismatch")
    development_start = datetime.fromisoformat(
        canonical_utc(payload["development_start"], field="development_start").replace(
            "Z", "+00:00"
        )
    )
    development_end = datetime.fromisoformat(
        canonical_utc(payload["development_end"], field="development_end").replace(
            "Z", "+00:00"
        )
    )
    if (
        payload["schema_version"] != "v17-prospective-gate-config-1"
        or payload["epoch_id"] != "v32-forward-l2-20260824T060000Z"
        or development_end - development_start != timedelta(hours=168)
        or int(payload["decision_cadence_seconds"]) != 3600
        or int(payload["maximum_common_gap_seconds"]) != 900
        or int(payload["minimum_symbols_per_hour"]) != 20
        or int(payload["minimum_hours_per_symbol"]) != 160
        or payload["recorder_schema_version"] != "v8-l2-snapshot-1"
    ):
        raise ValueError("gate config epoch or threshold invariant mismatch")
    if (
        payload["outcomes_opened"]
        or payload["trial_871_authorized"]
        or payload["trial_871_consumed"]
        or payload["candidate_frozen"]
        or payload["ready_to_start_paper"]
        or payload["a1"] != "NOT_STARTED"
        or payload["live_authorization"] != "LIVE_NOT_AUTHORIZED"
    ):
        raise ValueError("gate config safety invariant mismatch")
    return GateConfig(
        schema_version=str(payload["schema_version"]),
        epoch_id=str(payload["epoch_id"]),
        source_v32_git_sha=str(payload["source_v32_git_sha"]),
        boundary_path=str(payload["boundary_path"]),
        boundary_file_sha256=str(payload["boundary_file_sha256"]),
        boundary_canonical_sha256=str(payload["boundary_canonical_sha256"]),
        development_start=development_start,
        development_end=development_end,
        decision_cadence_seconds=int(payload["decision_cadence_seconds"]),
        maximum_common_gap_seconds=int(payload["maximum_common_gap_seconds"]),
        minimum_symbols_per_hour=int(payload["minimum_symbols_per_hour"]),
        minimum_hours_per_symbol=int(payload["minimum_hours_per_symbol"]),
        recorder_schema_version=str(payload["recorder_schema_version"]),
        strict_l2_fields=fields,
        expected_symbols=symbols,
        outcomes_opened=False,
        trial_871_authorized=False,
        trial_871_consumed=False,
        candidate_frozen=False,
        ready_to_start_paper=False,
        a1="NOT_STARTED",
        live_authorization="LIVE_NOT_AUTHORIZED",
    )
```

- [ ] **Step 6: Run tests and commit**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py
ruff check src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git add configs/v17_prospective_gate_v1.json configs/v17_prospective_gate_v1.json.sha256 src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git commit -m "feat: pin V17 prospective gate contract"
```

Expected: all checks pass and the commit contains only the four listed files.

### Task 2: Read finalized metadata with a strict projection

**Files:**
- Modify: `src/crypto_research/prospective_gate_v17.py`
- Modify: `tests/test_prospective_gate_v17.py`

**Interfaces:**
- Consumes: `GateConfig`, recorder metadata root, audit cutoff.
- Produces: `MetadataBatch` through `read_finalized_metadata(root, config, audit_cutoff) -> MetadataBatch`.

- [ ] **Step 1: Write failing sidecar/projection tests**

Add helpers that write one synthetic parquet and its raw-byte SHA-256 sidecar. The parquet may contain an `outcome_sentinel` column; monkeypatch `pandas.read_parquet` and assert its `columns` argument equals `list(STRICT_L2_FIELDS)`. Assert the returned rows contain no sentinel value.

Add these exact cases:

```python
def test_reader_verifies_sidecar_and_projects_only_strict_fields(tmp_path, monkeypatch) -> None:
    root, parquet = write_synthetic_l2_file(tmp_path, captured_at="2026-08-24T06:59:59Z")
    seen = {}
    real = pd.read_parquet

    def projected(path, *, columns):
        seen["columns"] = columns
        return real(path, columns=columns)

    monkeypatch.setattr(pd, "read_parquet", projected)
    batch = read_finalized_metadata(root, config_for_test(), audit_cutoff=utc("2026-08-24T07:00:00Z"))

    assert seen["columns"] == list(STRICT_L2_FIELDS)
    assert batch.rows[0]["symbol"] == "BTC/USDT:USDT"
    assert "outcome_sentinel" not in batch.rows[0]


def test_reader_rejects_missing_or_corrupt_sidecar(tmp_path) -> None:
    root, parquet = write_synthetic_l2_file(tmp_path, captured_at="2026-08-24T06:59:59Z")
    parquet.with_suffix(".parquet.sha256").write_text("bad\n")

    with pytest.raises(GateInputError, match="sidecar"):
        read_finalized_metadata(root, config_for_test(), audit_cutoff=utc("2026-08-24T07:00:00Z"))


def test_reader_lists_but_never_opens_active_wal(tmp_path, monkeypatch) -> None:
    root, _ = write_synthetic_l2_file(tmp_path, captured_at="2026-08-24T06:59:59Z")
    wal = root / "date=2026-08-24" / "symbol=BTC_USDT_USDT" / ".pending.jsonl"
    wal.write_text('{"outcome_sentinel": 999}\n')
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if Path(path).name == ".pending.jsonl":
            raise AssertionError("active WAL was opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    batch = read_finalized_metadata(root, config_for_test(), audit_cutoff=utc("2026-08-24T07:00:00Z"))

    assert batch.active_wals == ("date=2026-08-24/symbol=BTC_USDT_USDT/.pending.jsonl",)
```

- [ ] **Step 2: Run the focused tests and verify failure**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py -k "reader"
```

Expected: import/name failures for `MetadataBatch`, `GateInputError`, or `read_finalized_metadata`.

- [ ] **Step 3: Implement finalized-file evidence**

Add:

```python
import hashlib
import re
from dataclasses import dataclass
from datetime import date, timezone
from typing import Any

import pandas as pd


class GateInputError(ValueError):
    def __init__(self, message: str, *, failure_scope: str = "IMMUTABLE_INPUT") -> None:
        super().__init__(message)
        self.failure_scope = failure_scope


@dataclass(frozen=True)
class MetadataBatch:
    rows: tuple[dict[str, Any], ...]
    files: tuple[tuple[str, int, str], ...]
    active_wals: tuple[str, ...]
    excluded_row_count: int


_L2_FILE_NAME = re.compile(
    r"^l2_(?P<start>\d{4}-\d{2}-\d{2}T\d{6}\.\d{6}_0000)_"
    r"(?P<end>\d{4}-\d{2}-\d{2}T\d{6}\.\d{6}_0000)_"
    r"[0-9a-f]{16}\.parquet$"
)


def _partition_date(path: Path) -> date:
    value = path.parents[1].name
    try:
        return datetime.strptime(value.removeprefix("date="), "%Y-%m-%d").date()
    except ValueError as exc:
        raise GateInputError(f"unexpected L2 partition: {value}") from exc


def _file_capture_bounds(path: Path) -> tuple[datetime, datetime]:
    match = _L2_FILE_NAME.fullmatch(path.name)
    if match is None:
        raise GateInputError(f"unexpected L2 filename: {path.name}")

    def parse(value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%dT%H%M%S.%f_0000").replace(
            tzinfo=timezone.utc
        )

    return parse(match["start"]), parse(match["end"])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_finalized_metadata(
    root: str | Path,
    config: GateConfig,
    *,
    audit_cutoff: datetime,
) -> MetadataBatch:
    base = Path(root).resolve()
    cutoff = datetime.fromisoformat(canonical_utc(audit_cutoff, field="audit_cutoff").replace("Z", "+00:00"))
    if cutoff < config.development_start:
        raise GateInputError("audit cutoff precedes DEVELOPMENT")
    admission_cutoff = min(cutoff, config.development_end)
    admitted: list[dict[str, Any]] = []
    evidence: list[tuple[str, int, str]] = []
    excluded = 0

    for parquet in sorted(base.glob("date=*/symbol=*/*.parquet")):
        partition_date = _partition_date(parquet)
        if not config.development_start.date() <= partition_date <= admission_cutoff.date():
            continue
        file_start, file_end = _file_capture_bounds(parquet)
        if file_end < config.development_start or file_start > admission_cutoff:
            continue
        sidecar = parquet.with_suffix(parquet.suffix + ".sha256")
        if not sidecar.is_file():
            raise GateInputError(f"missing sidecar: {parquet.relative_to(base)}")
        expected = sidecar.read_text(encoding="utf-8").strip()
        actual = _sha256_file(parquet)
        if expected != actual:
            raise GateInputError(f"sidecar mismatch: {parquet.relative_to(base)}")
        frame = pd.read_parquet(parquet, columns=list(STRICT_L2_FIELDS))
        if tuple(frame.columns) != STRICT_L2_FIELDS:
            raise GateInputError("projected metadata schema mismatch")
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True, errors="raise")
        in_window = frame["captured_at"].ge(config.development_start) & frame["captured_at"].le(
            admission_cutoff
        )
        excluded += int((~in_window).sum())
        selected = frame.loc[in_window].copy()
        if selected.empty:
            continue
        evidence.append((parquet.relative_to(base).as_posix(), parquet.stat().st_size, actual))
        admitted.extend(selected.to_dict("records"))

    active = tuple(
        path.relative_to(base).as_posix()
        for path in sorted(base.glob("date=*/symbol=*/.pending.jsonl"))
        if config.development_start.date()
        <= _partition_date(path)
        <= admission_cutoff.date()
    )
    return MetadataBatch(tuple(admitted), tuple(evidence), active, excluded)
```

Before returning, validate every admitted row has exactly the nine keys, `data_version == config.recorder_schema_version`, symbol in the pinned universe, `event_time <= available_at <= captured_at`, unique identity `(data_version, source, symbol, captured_at, checksum)`, and non-decreasing capture time within each `(source, symbol)`. Repeated `source_id/update_id` remains valid.

- [ ] **Step 4: Add the remaining trust-boundary tests**

Test exact failure messages for:

- a returned projected frame with an extra nested field;
- mixed `data_version`;
- symbol outside the pinned universe;
- duplicate row identity;
- non-monotonic capture order;
- `available_at > captured_at`;
- a future row and a post-DEVELOPMENT row being excluded before evaluator admission, including during finalization grace;
- an audit cutoff before DEVELOPMENT being rejected;
- a corrupt finalized file whose recorder filename range is wholly before DEVELOPMENT being ignored;
- a corrupt finalized file whose recorder filename range overlaps DEVELOPMENT being rejected;
- an unexpected filename inside the DEVELOPMENT date partitions being rejected fail-closed;
- active WAL paths outside the DEVELOPMENT-through-cutoff date range being ignored;
- repeated update IDs remaining valid.

- [ ] **Step 5: Run tests and commit**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py -k "reader or sidecar or projection or identity"
ruff check src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git add src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git commit -m "feat: read finalized V17 metadata safely"
```

### Task 3: Compute exact DEVELOPMENT verdicts and canonical results

**Files:**
- Modify: `src/crypto_research/prospective_gate_v17.py`
- Modify: `tests/test_prospective_gate_v17.py`

**Interfaces:**
- Consumes: validated `GateConfig`, `MetadataBatch`, audit cutoff, boundary/config/evaluator/health hashes.
- Produces: `evaluate_v17_prospective_gate(...) -> dict[str, object]` with one of four statuses and deterministic `result_hash`.

- [ ] **Step 1: Write failing clean-window and progress tests**

Use synthetic rows at every hour-end minus one second for all 21 symbols.

```python
def test_seven_clean_days_are_eligible_but_167_hours_collect() -> None:
    config = config_for_test()
    full = evaluate_v17_prospective_gate(
        config=config,
        batch=clean_batch(config, hours=168),
        audit_cutoff=config.development_end,
        provenance=provenance_for_test(),
    )
    partial = evaluate_v17_prospective_gate(
        config=config,
        batch=clean_batch(config, hours=167),
        audit_cutoff=config.development_start + timedelta(hours=167),
        provenance=provenance_for_test(),
    )

    assert full["status"] == "DEVELOPMENT_ELIGIBLE"
    assert partial["status"] == "COLLECTING"
    assert full["completed_hours"] == 168
    assert full["per_symbol_hours"]["BTC/USDT:USDT"] == 168
    assert full["outcomes_opened"] is False
    assert full["trial_871_consumed"] is False
    assert full["READY_TO_START_PAPER"] is False
    assert full["A1"] == "NOT_STARTED"
    assert full["live_authorization"] == "LIVE_NOT_AUTHORIZED"
```

- [ ] **Step 2: Write failing boundary/coverage/gap tests**

Add exact cases:

- 19 symbols at one decision returns `RESET_REQUIRED` after the final boundary.
- 20 symbols at every decision satisfies the per-hour count, but the missing symbol must still reach 160 decisions.
- 159/168 for one symbol returns `RESET_REQUIRED`; 160/168 passes.
- a 900-second common gap does not reset; a 901-second gap returns `RESET_REQUIRED`.
- a common gap detected before the DEVELOPMENT end returns `RESET_REQUIRED` immediately.
- a partial current hour is excluded.
- an unfinished last-hour evidence file produces `COLLECTING` and lists the blocking relative path only through `development_end + 15 minutes`; after that exact grace boundary, failed coverage returns `RESET_REQUIRED`.
- corrupt/mixed/duplicate input maps to `INVALID_METADATA`, never `COLLECTING`.
- changing the absolute metadata root does not change `result_hash`; changing one declared file digest does.

- [ ] **Step 3: Run the evaluator tests and verify failure**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py -k "eligible or collect or coverage or gap or result_hash"
```

Expected: failure because the evaluator is not implemented.

- [ ] **Step 4: Implement the status algorithm**

Use these exact steps inside `evaluate_v17_prospective_gate`:

```python
def evaluate_v17_prospective_gate(
    *,
    config: GateConfig,
    batch: MetadataBatch,
    audit_cutoff: datetime,
    provenance: dict[str, object],
) -> dict[str, object]:
    cutoff = min(audit_cutoff, config.development_end)
    completed = int(
        (cutoff - config.development_start).total_seconds()
        // config.decision_cadence_seconds
    )
    decisions = tuple(
        config.development_start
        + timedelta(seconds=config.decision_cadence_seconds * (index + 1))
        for index in range(completed)
    )
    captures = sorted(
        datetime.fromisoformat(canonical_utc(row["captured_at"], field="captured_at").replace("Z", "+00:00"))
        for row in batch.rows
    )
    points = [config.development_start, *captures, cutoff]
    common_gap_seconds = max(
        ((right - left).total_seconds() for left, right in pairwise(points)),
        default=0.0,
    )

    per_hour: dict[str, int] = {}
    per_symbol = {symbol: 0 for symbol in config.expected_symbols}
    for decision in decisions:
        usable = set()
        for symbol in config.expected_symbols:
            prior = [
                row
                for row in batch.rows
                if row["symbol"] == symbol
                and row["captured_at"] <= decision
                and (decision - row["captured_at"]).total_seconds()
                <= config.maximum_common_gap_seconds
            ]
            if prior:
                usable.add(symbol)
                per_symbol[symbol] += 1
        per_hour[canonical_utc(decision, field="decision_time")] = len(usable)

    if common_gap_seconds > config.maximum_common_gap_seconds:
        status = "RESET_REQUIRED"
    coverage_failed = (
        min(per_hour.values(), default=0) < config.minimum_symbols_per_hour
        or min(per_symbol.values(), default=0) < config.minimum_hours_per_symbol
    )
    missing_last_symbols = {
        symbol
        for symbol in config.expected_symbols
        if per_symbol[symbol] < completed
    }
    blocking_wals = tuple(
        path
        for path in batch.active_wals
        if any(symbol.replace("/", "_").replace(":", "_") in path for symbol in missing_last_symbols)
    )
    finalization_deadline = config.development_end + timedelta(
        seconds=config.maximum_common_gap_seconds
    )

    if common_gap_seconds > config.maximum_common_gap_seconds:
        status = "RESET_REQUIRED"
    elif audit_cutoff < config.development_end:
        status = "COLLECTING"
    elif coverage_failed and blocking_wals and audit_cutoff <= finalization_deadline:
        status = "COLLECTING"
    elif coverage_failed:
        status = "RESET_REQUIRED"
    else:
        status = "DEVELOPMENT_ELIGIBLE"
```

Implement the loop efficiently by pre-grouping and sorting rows per symbol and advancing one index per hourly decision; do not keep the illustrative repeated scan. This is the same algorithm with `O(rows + 168 × symbols)` behavior.

Build the result with boundary/audit/provenance hashes, relative file tuples, completed-hour counts, per-symbol counts/coverage, max gaps, violations, accessed fields/ranges, excluded rows, blocking files, `failure_scope`, the hard safety invariants, and `result_hash = canonical_sha256(GATE_RESULT_DOMAIN, result_without_hash)`.

- [ ] **Step 5: Run all gate tests and commit**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py
ruff check src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
python -m compileall -q src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git diff --check
git add src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git commit -m "feat: enforce V17 prospective coverage gate"
```

### Task 4: Append complete weakness events without touching recorder paths

**Files:**
- Modify: `src/crypto_research/prospective_gate_v17.py`
- Modify: `tests/test_prospective_gate_v17.py`

**Interfaces:**
- Consumes: one gate result, epoch ID, run timestamp, output path.
- Produces: ten append-only JSONL events via `append_weakness_events(path, *, result, epoch_id, run_at)`.

- [ ] **Step 1: Write failing weakness/lifecycle tests**

Assert exactly one event for each category:

```python
EXPECTED_CATEGORIES = {
    "LEAKAGE",
    "DEPENDENCE",
    "MULTIPLE_TESTING",
    "DATA",
    "REGIME",
    "COST",
    "EXECUTION",
    "RISK",
    "REPRODUCIBILITY",
    "GOVERNANCE",
}
```

Every event must contain non-empty `event_id`, `run_result_hash`, `epoch_id`, `timestamp`, `severity`, `category`, `claim`, `evidence_references`, `root_cause`, `containment`, `remediation`, `retest`, `owner`, and `status`. Re-running with the same result/time must not append duplicate event IDs. A result with `failure_scope=IMMUTABLE_INPUT` must say the epoch is unusable; `TRANSIENT_IO` must preserve and link `prior_failure_event_id`.

- [ ] **Step 2: Add the recorder-root rejection test**

```python
def test_weakness_output_must_be_outside_recorder_root(tmp_path) -> None:
    recorder = tmp_path / "public_l2"
    recorder.mkdir()
    result = result_for_test("COLLECTING")

    with pytest.raises(ValueError, match="outside metadata root"):
        append_weakness_events(
            recorder / "weakness.jsonl",
            result=result,
            epoch_id="epoch",
            run_at=utc("2026-08-24T08:00:00Z"),
            metadata_root=recorder,
        )
```

- [ ] **Step 3: Implement durable append-only events**

Use `canonical_sha256("forward-l2-weakness-event-v1", event_without_id)` as `event_id`. Load only the target weakness log to deduplicate. Append with `json.dumps(..., sort_keys=True, separators=(",", ":"))`, flush, and `os.fsync`. Resolve both paths and reject `output == metadata_root` or `metadata_root in output.parents`.

- [ ] **Step 4: Run tests and commit**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py -k "weakness or lifecycle or recorder_root"
python -m pytest -q tests/test_prospective_gate_v17.py
git add src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py
git commit -m "feat: log prospective gate weaknesses"
```

### Task 5: Add the one-shot metadata-only CLI

**Files:**
- Create: `scripts/run_v17_prospective_gate.py`
- Modify: `tests/test_prospective_gate_v17.py`

**Interfaces:**
- Consumes: pinned boundary/config hashes, metadata root, optional health JSON, audit cutoff, output weakness path.
- Produces: canonical result JSON on stdout and weakness JSONL outside the metadata root; no process/service/state actions.

- [ ] **Step 1: Write the failing CLI surface test**

Parse the script AST and assert its argument names are exactly:

```python
{
    "--boundary-manifest",
    "--expected-boundary-file-sha256",
    "--gate-config",
    "--expected-gate-config-sha256",
    "--metadata-root",
    "--recorder-health",
    "--audit-cutoff",
    "--weakness-jsonl",
}
```

Assert the AST contains no calls named `write_text`, `unlink`, `replace`, `rename`, `kill`, `terminate`, `systemctl`, `service`, `Popen`, `run`, `create_order`, `cancel_order`, `transfer`, or `withdraw`. The allowed weakness writer is called through `append_weakness_events`, which rejects recorder-root paths.

- [ ] **Step 2: Run the CLI test and verify failure**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py -k "cli"
```

Expected: failure because the script does not exist.

- [ ] **Step 3: Implement the thin CLI**

```python
"""One-shot metadata-only V17 prospective gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from crypto_research.prospective_gate_v17 import (
    GateInputError,
    append_weakness_events,
    evaluate_v17_prospective_gate,
    load_gate_config,
    read_finalized_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-manifest", type=Path, required=True)
    parser.add_argument("--expected-boundary-file-sha256", required=True)
    parser.add_argument("--gate-config", type=Path, required=True)
    parser.add_argument("--expected-gate-config-sha256", required=True)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--recorder-health", type=Path)
    parser.add_argument("--audit-cutoff", required=True)
    parser.add_argument("--weakness-jsonl", type=Path, required=True)
    args = parser.parse_args()

    config = load_gate_config(args.gate_config, expected_hash=args.expected_gate_config_sha256)
    if args.boundary_manifest.as_posix() != config.boundary_path:
        raise SystemExit("boundary path mismatch")
    if args.expected_boundary_file_sha256 != config.boundary_file_sha256:
        raise SystemExit("boundary expected hash mismatch")
    boundary_bytes = args.boundary_manifest.read_bytes()
    boundary_file_hash = hashlib.sha256(boundary_bytes).hexdigest()
    if boundary_file_hash != args.expected_boundary_file_sha256:
        raise SystemExit("boundary file hash mismatch")
    boundary_payload = json.loads(boundary_bytes)
    boundary_canonical_hash = hashlib.sha256(
        json.dumps(
            boundary_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if boundary_canonical_hash != config.boundary_canonical_sha256:
        raise SystemExit("boundary canonical hash mismatch")
    cutoff = datetime.fromisoformat(args.audit_cutoff.replace("Z", "+00:00"))
    batch = read_finalized_metadata(args.metadata_root, config, audit_cutoff=cutoff)
    health_hash = (
        hashlib.sha256(args.recorder_health.read_bytes()).hexdigest()
        if args.recorder_health is not None
        else None
    )
    module_path = Path(__import__(
        "crypto_research.prospective_gate_v17",
        fromlist=["__file__"],
    ).__file__)
    result = evaluate_v17_prospective_gate(
        config=config,
        batch=batch,
        audit_cutoff=cutoff,
        provenance={
            "source_v32_git_sha": config.source_v32_git_sha,
            "boundary_file_sha256": boundary_file_hash,
            "boundary_canonical_sha256": boundary_canonical_hash,
            "gate_config_sha256": args.expected_gate_config_sha256,
            "evaluator_source_hashes": {
                "src/crypto_research/prospective_gate_v17.py": hashlib.sha256(
                    module_path.read_bytes()
                ).hexdigest(),
                "scripts/run_v17_prospective_gate.py": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
            },
            "recorder_health_sha256": health_hash,
        },
    )
    append_weakness_events(
        args.weakness_jsonl,
        result=result,
        epoch_id=config.epoch_id,
        run_at=cutoff,
        metadata_root=args.metadata_root,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Catch `GateInputError` around the reader, convert it into an `INVALID_METADATA` result with its exact `failure_scope`, append the same ten weakness categories, print the result, and return 0. Invocation errors and unreadable mandatory paths exit nonzero. Gate verdicts never change the process exit code.

- [ ] **Step 4: Run focused and lane tests**

```bash
python -m pytest -q tests/test_prospective_gate_v17.py
ruff check src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py scripts/run_v17_prospective_gate.py
python -m compileall -q src/crypto_research/prospective_gate_v17.py tests/test_prospective_gate_v17.py scripts/run_v17_prospective_gate.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit the CLI**

```bash
git add scripts/run_v17_prospective_gate.py tests/test_prospective_gate_v17.py
git commit -m "feat: add metadata-only V17 gate CLI"
```

### Task 6: Lane A acceptance verification

**Files:**
- May create outside recorder root: `artifacts/multi_asset_v11/v17_gate_20260824T080000Z.json`
- May append outside recorder root: `artifacts/multi_asset_v11/v17_gate_weakness.jsonl`
- Do not commit a new readiness version until the integrator confirms this is a meaningful accepted checkpoint.

**Interfaces:**
- Consumes: completed Lane A commits and real metadata projection only.
- Produces: current `COLLECTING` audit, exact tests/static evidence, clean worktree after explicitly deciding whether to version the generated audit.

- [ ] **Step 1: Run all synthetic Lane A tests**

```bash
python -m pytest -q tests/test_canonical_json.py tests/test_prospective_gate_v17.py
```

Expected: all tests pass.

- [ ] **Step 2: Run one real metadata-only audit at a fixed completed cutoff**

```bash
python scripts/run_v17_prospective_gate.py \
  --boundary-manifest paper_readiness_versions/version_32/10_forward_l2_prospective_boundary.json \
  --expected-boundary-file-sha256 019b997e99124ceda93a7bedaa9cb91d9651d820ece160cbfbbb918b60b83690 \
  --gate-config configs/v17_prospective_gate_v1.json \
  --expected-gate-config-sha256 "$(tr -d '\n' < configs/v17_prospective_gate_v1.json.sha256)" \
  --metadata-root /home/duypham/workspace/InvestMent-v9-local-data/public_l2 \
  --recorder-health /home/duypham/workspace/InvestMent-v9-local-data/public_l2/recorder_health.json \
  --audit-cutoff 2026-08-24T08:00:00Z \
  --weakness-jsonl artifacts/multi_asset_v11/v17_gate_weakness.jsonl \
  > artifacts/multi_asset_v11/v17_gate_20260824T080000Z.json
```

Expected: `status == "COLLECTING"`; every safety invariant remains false/unauthorized; no outcome reader or WAL evidence is opened.

- [ ] **Step 3: Run the repository contract**

```bash
python -m pytest -q
ruff check src tests scripts
python -m compileall -q src tests scripts
python -m json.tool configs/v17_prospective_gate_v1.json >/dev/null
python -m json.tool artifacts/multi_asset_v11/v17_gate_20260824T080000Z.json >/dev/null
git diff --check
git status --short
```

Expected: all verification commands pass. Generated audit files are the only possible uncommitted files; the integrator either commits them as an accepted checkpoint or removes only those newly generated files after reviewing their exact paths.

- [ ] **Step 4: Verify recorder processes without controlling them**

Read process and health metadata only. Confirm the known L2 and positioning recorder processes remain present and no source/config under their running worktree changed. Do not signal, restart, flush, rotate, or stop either process.
