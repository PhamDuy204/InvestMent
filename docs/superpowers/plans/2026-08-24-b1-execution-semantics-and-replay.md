# B1 Execution Semantics and Deterministic Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct partial-fill accounting, persist immutable market provenance and rejected decisions, verify an engineering-only freeze manifest, and reproduce paper journal hashes offline without any live-trading surface.

**Architecture:** Extend the existing single paper path rather than creating a second broker or simulator. A pure observation/intent module normalizes time and order-book evidence; `ExecutionSimulatorV8` retains its observed-depth walk but returns explicit statuses; `ShadowPaperEngine` journals accepted/rejected decisions with a hash chain and filled-only accounting; `PaperRuntimeV9` validates, recovers, and replays deterministic events. A narrow CCXT adapter exposes only public order-book reads.

**Tech Stack:** Python 3.11 standard library (`dataclasses`, `datetime`, `decimal`, `hashlib`, `json`), existing CCXT, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-24-paper-readiness-and-multi-market-design.md`

**Depends on:** `docs/superpowers/plans/2026-08-24-shared-strict-provenance-foundation.md` completed and green.

## Global Constraints

- Preserve `PaperRuntimeV9 → ShadowPaperEngine → SimulatedBroker → ExecutionSimulatorV8` as the only paper path.
- No new simulator, broker, dependency, account credential, authenticated endpoint, private endpoint, live order, cancel, leverage, borrow, repay, transfer, or withdrawal operation.
- B1 is engineering-only; `A1=NOT_STARTED`, trial 871 untouched, paper readiness false, and `LIVE_NOT_AUTHORIZED`.
- Use synthetic books/outcomes only in tests; do not read V17 DEVELOPMENT/UNTOUCHED outcomes.
- Preserve observed-depth walking and never extrapolate beyond available levels.
- Persist economic quantities as finite canonical base-10 strings; timestamps use fixed-microsecond UTC RFC 3339.
- Require `event_time <= source_available_at <= captured_at <= decision_time <= execution_time`; equality is allowed.
- A freeze manifest pins `manifest_id`, `manifest_hash`, `max_staleness_seconds`, `engineering_only=true`, and `a1_enabled=false`.
- `requested_notional_quote > 0`; `0 < filled_notional_quote <= requested_notional_quote` for accepted fills.
- `filled_exposure = requested_exposure × filled_notional_quote / requested_notional_quote`; short signs must survive.
- Only filled notional/exposure enter fees, funding, position recovery, and PnL once.
- Rejected decisions are immutable, positionless, and cannot receive outcomes.
- Shared files are integrator-owned and edited serially: `point_in_time_v8.py`, `execution_v8.py`, `governance_v9.py`, `shadow_paper_v8.py`, `paper_v9.py`, `run_v9_paper.py`, and their existing tests.
- No new dependency.
- Use the repo-local environment bootstrapped by the foundation plan; every fresh agent runs `source .venv/bin/activate` before task commands.

---

### Task 1: Add a reusable execution time chain and immutable observation/intent

**Files:**
- Modify: `src/crypto_research/point_in_time_v8.py:23-63`
- Modify: `tests/test_point_in_time_v8.py`
- Create: `src/crypto_research/execution_observation_v1.py`
- Create: `tests/test_execution_observation_v1.py`

**Interfaces:**
- Consumes: shared strict canonical functions and raw public bid/ask levels.
- Produces: `validate_execution_time_chain(...) -> tuple[str, str, str, str, str]`, `ExecutionObservationV1`, `ExecutionIntentV1`, `build_execution_observation`, `build_execution_intent`, `verify_execution_observation`, and stable observation/intent hashes.

- [ ] **Step 1: Write failing PIT time-chain tests**

```python
from crypto_research.point_in_time_v8 import validate_execution_time_chain


def test_execution_time_chain_allows_equal_utc_boundaries() -> None:
    stamp = "2026-08-24T06:00:00Z"
    assert validate_execution_time_chain(
        event_time=stamp,
        source_available_at=stamp,
        captured_at=stamp,
        decision_time=stamp,
        execution_time=stamp,
    ) == ("2026-08-24T06:00:00.000000Z",) * 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_time", "2026-08-24T06:00:02Z"),
        ("source_available_at", "2026-08-24T06:00:03Z"),
        ("captured_at", "2026-08-24T06:00:04Z"),
        ("decision_time", "2026-08-24T06:00:05Z"),
    ],
)
def test_execution_time_chain_rejects_every_inversion(field: str, value: str) -> None:
    values = {
        "event_time": "2026-08-24T06:00:00Z",
        "source_available_at": "2026-08-24T06:00:01Z",
        "captured_at": "2026-08-24T06:00:02Z",
        "decision_time": "2026-08-24T06:00:03Z",
        "execution_time": "2026-08-24T06:00:04Z",
    }
    values[field] = value
    if field == "event_time":
        values["source_available_at"] = "2026-08-24T06:00:01Z"
    with pytest.raises(ValueError, match="time order"):
        validate_execution_time_chain(**values)
```

- [ ] **Step 2: Run the PIT tests and verify failure**

```bash
python -m pytest -q tests/test_point_in_time_v8.py -k "execution_time_chain"
```

Expected: import fails because the new helper is absent.

- [ ] **Step 3: Add the minimal shared helper**

```python
from crypto_research.canonical_json import canonical_utc


def validate_execution_time_chain(
    *,
    event_time: datetime | str,
    source_available_at: datetime | str,
    captured_at: datetime | str,
    decision_time: datetime | str,
    execution_time: datetime | str,
) -> tuple[str, str, str, str, str]:
    normalized = tuple(
        canonical_utc(value, field=field)
        for field, value in (
            ("event_time", event_time),
            ("source_available_at", source_available_at),
            ("captured_at", captured_at),
            ("decision_time", decision_time),
            ("execution_time", execution_time),
        )
    )
    parsed = tuple(pd.Timestamp(value) for value in normalized)
    if any(left > right for left, right in zip(parsed, parsed[1:])):
        raise ValueError("execution time order must be event <= available <= captured <= decision <= execution")
    return normalized
```

Keep the existing DataFrame functions unchanged.

- [ ] **Step 4: Write failing observation and intent tests**

```python
from decimal import Decimal

from crypto_research.execution_observation_v1 import (
    build_execution_intent,
    build_execution_observation,
    verify_execution_observation,
)


def test_observation_normalizes_book_and_hashes_canonical_evidence() -> None:
    observation = build_execution_observation(
        venue="binanceusdm",
        instrument_id="BTC/USDT:USDT",
        event_time="2026-08-24T06:00:00Z",
        source_available_at="2026-08-24T06:00:00.100000Z",
        captured_at="2026-08-24T06:00:00.100000Z",
        decision_time="2026-08-24T06:00:00.200000Z",
        execution_time="2026-08-24T06:00:00.300000Z",
        source_id="book-1",
        update_id="101",
        bids=[[99, 2], [100, 1]],
        asks=[[102, 2], [101, 1]],
    )

    assert observation.bids == (("100", "1"), ("99", "2"))
    assert observation.asks == (("101", "1"), ("102", "2"))
    assert len(observation.book_checksum) == 64
    verify_execution_observation(observation, max_staleness_seconds=Decimal("0.2"))


def test_intent_requires_exposure_notional_nav_consistency_and_side_sign() -> None:
    intent = build_execution_intent(
        candidate_manifest_id="engineering-v1",
        candidate_manifest_hash="a" * 64,
        requested_exposure="-0.25",
        requested_notional_quote="250",
        nav_before_quote="1000",
        side="sell",
        signal="-0.5",
    )
    assert intent.requested_exposure == "-0.25"

    with pytest.raises(ValueError, match="notional"):
        build_execution_intent(
            candidate_manifest_id="engineering-v1",
            candidate_manifest_hash="a" * 64,
            requested_exposure="-0.25",
            requested_notional_quote="200",
            nav_before_quote="1000",
            side="sell",
            signal="-0.5",
        )
```

Add tests for empty/crossed books and their exact statuses, zero/negative quantities, duplicate prices, blank venue/instrument/source/update identity, source-availability age and exchange-event age at exact stale equality/pass and one microsecond over/fail, tampered checksum, and buy/positive plus sell/negative sign consistency.

- [ ] **Step 5: Implement the pure observation module**

Use these exact public types:

```python
@dataclass(frozen=True)
class ExecutionObservationV1:
    schema_version: str
    venue: str
    instrument_id: str
    event_time: str
    source_available_at: str
    captured_at: str
    decision_time: str
    execution_time: str
    source_id: str
    update_id: str
    bids: tuple[tuple[str, str], ...]
    asks: tuple[tuple[str, str], ...]
    book_checksum: str
    checksum_encoding: str = "execution-observation-v1-sha256"


@dataclass(frozen=True)
class ExecutionIntentV1:
    schema_version: str
    candidate_manifest_id: str
    candidate_manifest_hash: str
    requested_exposure: str
    requested_notional_quote: str
    nav_before_quote: str
    side: str
    signal: str
    intent_hash: str
```

Define `ObservationRejectedV1(ValueError)` with a `.status` field. Normalize each level with `canonical_decimal`; map malformed/checksum evidence to `REJECTED_INVALID_OBSERVATION`, empty depth to `REJECTED_EMPTY_BOOK`, crossed depth to `REJECTED_CROSSED_BOOK`, time-order failure to `REJECTED_INVALID_TIME`, and excess age to `REJECTED_STALE_DATA`. Reject non-positive price/quantity, duplicate price levels, empty sides, and `best_bid >= best_ask`. Sort bids descending and asks ascending. Compute `book_checksum` over the observation mapping without `book_checksum` using domain `execution-observation-v1`. Compute `intent_hash` over the intent mapping without `intent_hash` using domain `execution-intent-v1`. `verify_execution_observation` recomputes the checksum, calls `validate_execution_time_chain`, and enforces both `decision_time - source_available_at <= max_staleness_seconds` and `captured_at - event_time <= max_staleness_seconds`; this prevents a freshly captured but already stale exchange snapshot from passing.

- [ ] **Step 6: Run focused tests and commit**

```bash
python -m pytest -q tests/test_point_in_time_v8.py tests/test_execution_observation_v1.py
ruff check src/crypto_research/point_in_time_v8.py src/crypto_research/execution_observation_v1.py tests/test_point_in_time_v8.py tests/test_execution_observation_v1.py
git add src/crypto_research/point_in_time_v8.py src/crypto_research/execution_observation_v1.py tests/test_point_in_time_v8.py tests/test_execution_observation_v1.py
git commit -m "feat: add immutable execution observations"
```

### Task 2: Give the existing simulator explicit fill/reject statuses

**Files:**
- Modify: `src/crypto_research/execution_v8.py:157-274`
- Modify: `tests/test_execution_v8.py:122-183`

**Interfaces:**
- Consumes: existing `simulate_market_order` arguments.
- Produces: unchanged depth-walk economics plus `ExecutionResultV8.status` and `ExecutionRejectedV8.status`.

- [ ] **Step 1: Write failing status tests**

```python
from crypto_research.execution_v8 import (
    ExecutionRejectedV8,
    ExecutionSimulatorV8,
)


def test_simulator_reports_full_and_partial_fill_status() -> None:
    simulator = ExecutionSimulatorV8()
    book = {"bids": [[99.0, 1.0]], "asks": [[100.0, 1.0]]}

    full = simulator.simulate_market_order(target_notional=100.0, side="buy", book=book)
    partial = simulator.simulate_market_order(target_notional=250.0, side="buy", book=book)

    assert full.status == "FILLED"
    assert partial.status == "PARTIALLY_FILLED"


@pytest.mark.parametrize(
    "book,status",
    [
        ({"bids": [], "asks": []}, "REJECTED_EMPTY_BOOK"),
        ({"bids": [[101, 1]], "asks": [[100, 1]]}, "REJECTED_CROSSED_BOOK"),
    ],
)
def test_simulator_raises_structured_book_rejection(book, status) -> None:
    with pytest.raises(ExecutionRejectedV8) as caught:
        ExecutionSimulatorV8().simulate_market_order(
            target_notional=100,
            side="buy",
            book=book,
        )
    assert caught.value.status == status


@pytest.mark.parametrize("notional", [0, -1, float("nan"), float("inf")])
def test_simulator_rejects_invalid_notional_with_one_status(notional) -> None:
    with pytest.raises(ExecutionRejectedV8) as caught:
        ExecutionSimulatorV8().simulate_market_order(
            target_notional=notional,
            side="buy",
            book={"bids": [[99, 1]], "asks": [[100, 1]]},
        )
    assert caught.value.status == "REJECTED_INVALID_NOTIONAL"
```

- [ ] **Step 2: Run the simulator tests and verify failure**

```bash
python -m pytest -q tests/test_execution_v8.py -k "status or structured or invalid_notional"
```

Expected: failures because status and exception are absent.

- [ ] **Step 3: Implement the smallest shared fix**

```python
class ExecutionRejectedV8(ValueError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
```

Add `status: str` as the first `ExecutionResultV8` field. Raise:

- `REJECTED_INVALID_NOTIONAL` for non-finite/non-positive target;
- `REJECTED_EMPTY_BOOK` for empty executable depth;
- `REJECTED_CROSSED_BOOK` for crossed depth.

Return `FILLED` when `remaining <= _EPS`, otherwise `PARTIALLY_FILLED`. Do not alter VWAP, depth, fee, spread, latency, or no-extrapolation formulas.

- [ ] **Step 4: Run tests and commit**

```bash
python -m pytest -q tests/test_execution_v8.py
git add src/crypto_research/execution_v8.py tests/test_execution_v8.py
git commit -m "fix: classify simulated fills and rejects"
```

### Task 3: Verify a pinned engineering-only execution freeze

**Files:**
- Create: `configs/v9_engineering_execution_freeze_v1.json`
- Create: `configs/v9_engineering_execution_freeze_v1.json.sha256`
- Modify: `src/crypto_research/governance_v9.py:40-78`
- Modify: `tests/test_v9_governance.py:45-60`

**Interfaces:**
- Consumes: manifest path plus externally pinned canonical hash.
- Produces: `VerifiedExecutionFreezeV1` through `verify_execution_freeze_manifest(path, expected_hash)`.

- [ ] **Step 1: Write the exact engineering manifest**

```json
{
  "schema_version": "v1-engineering-execution-freeze-1",
  "manifest_id": "v9-engineering-smoke-only",
  "candidate_manifest_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "max_staleness_seconds": "30",
  "engineering_only": true,
  "a1_enabled": false,
  "ready_to_start_paper": false,
  "trial_871_authorized": false,
  "live_authorization": "LIVE_NOT_AUTHORIZED"
}
```

Add both hashes with this exact command:

```bash
python - <<'PY'
import json
from pathlib import Path
from crypto_research.canonical_json import canonical_sha256

path = Path("configs/v9_engineering_execution_freeze_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))
payload.pop("manifest_hash", None)
payload["manifest_hash"] = canonical_sha256(
    "execution-freeze-manifest-v1",
    payload,
)
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
envelope = canonical_sha256("execution-freeze-envelope-v1", payload)
path.with_suffix(path.suffix + ".sha256").write_text(envelope + "\n", encoding="utf-8")
PY
```

Never type either derived hash manually.

- [ ] **Step 2: Write failing verifier tests**

```python
from crypto_research.governance_v9 import (
    VerifiedExecutionFreezeV1,
    verify_execution_freeze_manifest,
)


def test_engineering_execution_freeze_is_verified_but_never_enables_a1() -> None:
    freeze = verify_execution_freeze_manifest(MANIFEST, expected_hash=ENVELOPE_HASH)

    assert isinstance(freeze, VerifiedExecutionFreezeV1)
    assert freeze.engineering_only is True
    assert freeze.a1_enabled is False
    assert freeze.ready_to_start_paper is False
    assert freeze.live_authorization == "LIVE_NOT_AUTHORIZED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_staleness_seconds", "31"),
        ("manifest_id", "forged"),
        ("a1_enabled", True),
        ("ready_to_start_paper", True),
        ("trial_871_authorized", True),
        ("live_authorization", "LIVE"),
    ],
)
def test_execution_freeze_mutation_or_authorization_fails_closed(tmp_path, field, value) -> None:
    payload = json.loads(MANIFEST.read_text())
    payload[field] = value
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError):
        verify_execution_freeze_manifest(path, expected_hash=ENVELOPE_HASH)
```

- [ ] **Step 3: Implement the verified type and verifier**

```python
@dataclass(frozen=True)
class VerifiedExecutionFreezeV1:
    manifest_id: str
    manifest_hash: str
    candidate_manifest_hash: str
    max_staleness_seconds: Decimal
    engineering_only: bool
    a1_enabled: bool
    ready_to_start_paper: bool
    live_authorization: str
```

The verifier must:

1. reject a full-envelope hash mismatch;
2. pop `manifest_hash`, recompute it over the remaining payload, and compare;
3. require the exact schema version;
4. require finite `max_staleness_seconds >= 0`;
5. require `engineering_only is True`, `a1_enabled is False`, `ready_to_start_paper is False`, `trial_871_authorized is False`, and `LIVE_NOT_AUTHORIZED`;
6. return the frozen dataclass.

Keep `build_candidate_freeze_payload` and `verify_candidate_freeze` unchanged for historical callers, but B1 runtime stops accepting their caller-provided boolean/hash surface.

- [ ] **Step 4: Run tests and commit**

```bash
python -m pytest -q tests/test_v9_governance.py
ruff check src/crypto_research/governance_v9.py tests/test_v9_governance.py
git add configs/v9_engineering_execution_freeze_v1.json configs/v9_engineering_execution_freeze_v1.json.sha256 src/crypto_research/governance_v9.py tests/test_v9_governance.py
git commit -m "feat: verify engineering execution freeze"
```

### Task 4: Journal filled-only decisions, rejects, cash flows, and a hash chain

**Files:**
- Modify: `src/crypto_research/shadow_paper_v8.py:5-181`
- Modify: `tests/test_shadow_paper_v8.py`

**Interfaces:**
- Consumes: verified observation, intent, freeze, existing simulator.
- Produces: `record_decision(observation, intent, freeze)`, `append_outcome(decision_id, evaluated_at, horizon_hours, realized_return, funding_rate)`, and `verify_journal(path)` with canonical row hashes.

- [ ] **Step 1: Replace direct-argument tests with immutable inputs**

Create test helpers `observation_for_test`, `intent_for_test`, and `freeze_for_test`. Write a partial buy where requested notional is 250 quote, observed ask depth fills 100 quote, requested exposure is 0.25, and NAV is 1000.

Assert:

```python
assert row["execution_status"] == "PARTIALLY_FILLED"
assert row["requested_exposure"] == "0.25"
assert row["filled_notional_quote"] == "100"
assert row["unfilled_notional_quote"] == "150"
assert row["filled_exposure"] == "0.1"
assert Decimal(row["fee_quote"]) >= 0
assert row["evidence_class"] == "ENGINEERING_ONLY"
assert len(row["observation_hash"]) == 64
assert len(row["intent_hash"]) == 64
assert len(row["fill_hash"]) == 64
assert len(row["row_hash"]) == 64
```

Add the signed short equivalent and exact full fill.

- [ ] **Step 2: Write failing reject and journal-integrity tests**

For empty/crossed/invalid notional, stale data, inverted time, invalid observation checksum, freeze/intent mismatch, and duplicate update identity, assert one `DECISION` row with the exact mapped `REJECTED_*` status, `accepted=false`, `filled_exposure="0"`, and no position. Reusing the same `(venue, instrument_id, source_id, update_id)` must append one `REJECTED_DUPLICATE_UPDATE`, not a second accepted decision.

Tamper one persisted price or row hash and assert:

```python
with pytest.raises(ValueError, match="journal hash"):
    verify_journal(path)
```

Reorder two rows and assert a journal-order failure.

- [ ] **Step 3: Write failing filled-only outcome test**

For the 40% long fill above, append a synthetic 10% realized return and `funding_rate="0.0025"`; the engine derives the filled-only signed funding cash flow and asserts:

```python
assert outcome["price_pnl_quote"] == "10"
assert outcome["funding_cashflow_quote"] == "-0.25"
assert Decimal(outcome["execution_cost_quote"]) == Decimal(row["execution_cost_quote"])
assert Decimal(outcome["net_pnl_quote"]) == (
    Decimal("10")
    + Decimal("-0.25")
    - Decimal(row["execution_cost_quote"])
)
assert Decimal(outcome["paper_pnl_return"]) == (
    Decimal(outcome["net_pnl_quote"]) / Decimal("1000")
)
```

Assert a rejected decision cannot receive an outcome and a second outcome for the same decision fails.

- [ ] **Step 4: Run tests and verify current accounting fails**

```bash
python -m pytest -q tests/test_shadow_paper_v8.py
```

Expected: failures show the current full-target `target_exposure` accounting bug.

- [ ] **Step 5: Implement one canonical journal path**

Change `SimulatedBroker.simulate` to serialize `ExecutionResultV8` economic floats through `canonical_decimal`; keep counts/booleans as integers/booleans.

Change `ShadowPaperEngine.record_decision` to this interface:

```python
def record_decision(
    self,
    *,
    observation: ExecutionObservationV1,
    intent: ExecutionIntentV1,
    freeze: VerifiedExecutionFreezeV1,
) -> dict[str, Any]:
    ...
```

Exact algorithm:

1. verify observation checksum/time/staleness using the freeze;
2. map intent manifest ID/hash mismatch to `REJECTED_INVALID_FREEZE` and side/notional mismatch to `REJECTED_INVALID_NOTIONAL`;
3. map `ObservationRejectedV1` to its exact `REJECTED_INVALID_OBSERVATION`, `REJECTED_EMPTY_BOOK`, `REJECTED_CROSSED_BOOK`, `REJECTED_INVALID_TIME`, or `REJECTED_STALE_DATA` status;
4. map duplicate observation identity to `REJECTED_DUPLICATE_UPDATE`;
5. call the existing broker only after validation and catch `ExecutionRejectedV8`;
6. build every mapped rejection as one immutable decision row with zero filled values and no position;
7. derive `latency_ms = int((execution_time - decision_time) / timedelta(milliseconds=1))`, pass the canonical book to the existing broker with `decision_mid=None`, and preserve the full microsecond timestamps separately;
8. for an accepted fill compute `fill_ratio = filled_notional_quote / requested_notional_quote`, `filled_exposure = requested_exposure × fill_ratio`, `fee_quote = filled_notional_quote × fee_bps / 10_000`, and signed `execution_cost_quote = filled_notional_quote × total_cost_bps / 10_000`;
9. compute observation, intent, and fill hashes;
10. set `attempt_sequence` to the zero-based count of existing decision rows and compute unique deterministic `decision_id` over those hashes, freeze identity, and `attempt_sequence`; a duplicate retry therefore cannot collide with the original accepted decision;
11. persist the complete canonical observation and intent mappings, `attempt_sequence`, and all filled-only quantities, then set `previous_row_hash` to the prior row hash or 64 zeroes;
12. compute `row_hash` over the row without `row_hash` using domain `paper-journal-row-v1`;
13. append/fsync once.

`verify_journal` recomputes every observation/intent/fill/decision/row hash, the exact contiguous `attempt_sequence`, and the chain; rejects duplicate decision IDs, duplicate accepted observation identities, rejected rows with nonzero fill/position, outcomes linked to rejected or unknown decisions, duplicate outcomes, and non-monotonic decision/execution time; and returns parsed rows only after all checks pass.

`append_outcome` accepts:

```python
def append_outcome(
    self,
    *,
    decision_id: str,
    evaluated_at: datetime,
    horizon_hours: int,
    realized_return: str,
    funding_rate: str = "0",
) -> dict[str, Any]:
    ...
```

It reads `nav_before_quote`, `filled_notional_quote`, `filled_exposure`, and `execution_cost_quote` from the decision; derives `price_pnl_quote = filled_exposure × nav_before_quote × realized_return`, `funding_cashflow_quote = -sign(filled_exposure) × filled_notional_quote × funding_rate`, `net_pnl_quote = price_pnl_quote + funding_cashflow_quote - execution_cost_quote`, and `paper_pnl_return = net_pnl_quote / nav_before_quote`; chains/hashes the outcome row; and refuses rejected/unknown/duplicate/immature outcomes. `execution_cost_quote` already includes fees, while `fee_quote` is reported as an attribution component and is not subtracted a second time. All arithmetic in the journal/outcome layer uses `Decimal`, not binary floats.

- [ ] **Step 6: Run tests and commit**

```bash
python -m pytest -q tests/test_execution_v8.py tests/test_shadow_paper_v8.py
ruff check src/crypto_research/execution_v8.py src/crypto_research/shadow_paper_v8.py tests/test_execution_v8.py tests/test_shadow_paper_v8.py
git add src/crypto_research/shadow_paper_v8.py tests/test_shadow_paper_v8.py
git commit -m "fix: account paper decisions by filled quantity"
```

### Task 5: Wire runtime recovery and deterministic offline replay

**Files:**
- Modify: `src/crypto_research/paper_v9.py:57-174`
- Modify: `tests/test_paper_v9.py:17-107`

**Interfaces:**
- Consumes: observation/intent/freeze objects and canonical journal rows.
- Produces: filled-only `process_decision`, verified `recover_state`, and `replay(events, freeze) -> tuple[str, ...]`.

- [ ] **Step 1: Write failing runtime/restart tests**

Update `_runtime` to stop accepting `max_staleness_seconds`; staleness comes only from the freeze. Process a 40% partial fill, restart, and assert:

```python
assert state["position_exposure"] == "0.1"
assert state["accepted_decision_count"] == 1
assert state["rejected_decision_count"] == 0
assert state["filled_notional_total_quote"] == "100"
assert state["unfilled_notional_total_quote"] == "150"
assert state["last_execution_status"] == "PARTIALLY_FILLED"
```

Process an empty/crossed rejection and assert state exposure/equity do not change while the rejected counter increments.

- [ ] **Step 2: Write failing replay/tamper tests**

Use two fixed synthetic observation/intent pairs and two fresh runtime directories:

```python
first_hashes = first.replay(events, freeze=freeze_for_test())
second_hashes = second.replay(events, freeze=freeze_for_test())

assert first_hashes == second_hashes
assert first.recover_state() == second.recover_state()
```

Then change one ask quantity and assert hashes differ. Reorder events or duplicate update identity and assert failure. Tamper a journal row before restart and assert `recover_state` fails before producing state.

- [ ] **Step 3: Run runtime tests and verify failure**

```bash
python -m pytest -q tests/test_paper_v9.py -k "partial or restart or replay or tamper or reject"
```

Expected: failures under the old loose argument API/full-target recovery.

- [ ] **Step 4: Implement the minimal runtime API**

```python
def process_decision(
    self,
    *,
    observation: ExecutionObservationV1,
    intent: ExecutionIntentV1,
    freeze: VerifiedExecutionFreezeV1,
) -> dict[str, Any]:
    try:
        row = self.engine.record_decision(
            observation=observation,
            intent=intent,
            freeze=freeze,
        )
    except Exception as exc:
        self._health(
            "BLOCKED_ERROR",
            updated_at=observation.execution_time,
            error_type=type(exc).__name__,
        )
        raise
    state = self.recover_state()
    _atomic_json(self.state_path, state)
    self._health(
        "HEALTHY" if row["accepted"] else "REJECTED",
        updated_at=observation.execution_time,
        last_decision_id=row["decision_id"],
        execution_status=row["execution_status"],
    )
    return row
```

Change `_health` to require an explicit canonical `updated_at`; it must never call `datetime.now`. `process_decision` passes `observation.execution_time`, so replayed health artifacts are deterministic and offline.

`recover_state` must call `verify_journal` first, sum quote values with `Decimal`, use only accepted decisions for the last position, count accepted/rejected separately, add each outcome `net_pnl_quote` once to initial equity, and serialize economic state values with `canonical_decimal`.

`replay` iterates a fixed `Sequence[tuple[ExecutionObservationV1, ExecutionIntentV1]]`, rejects non-monotonic execution times and duplicate observation identity before processing, calls no clock/network/transport, and returns the tuple of persisted `row_hash` values.

- [ ] **Step 5: Run tests and commit**

```bash
python -m pytest -q tests/test_shadow_paper_v8.py tests/test_paper_v9.py
ruff check src/crypto_research/paper_v9.py tests/test_paper_v9.py
git add src/crypto_research/paper_v9.py tests/test_paper_v9.py
git commit -m "feat: replay verified paper decisions offline"
```

### Task 6: Restrict public market data and update the engineering CLI

**Files:**
- Create: `src/crypto_research/public_market_data_v1.py`
- Create: `tests/test_public_market_data_v1.py`
- Modify: `src/crypto_research/paper_v9.py:38-54`
- Modify: `scripts/run_v9_paper.py:16-59`
- Modify: `tests/test_paper_v9.py:109-200`
- Modify: `tests/test_v8_live_order_safety.py:6-29`

**Interfaces:**
- Consumes: one allowlisted venue/instrument/limit and public CCXT order-book response.
- Produces: `CcxtPublicBookTransportV1.fetch_order_book`, metadata capture, immutable observation construction, and an always-engineering CLI.

- [ ] **Step 1: Write failing transport allowlist tests**

```python
from crypto_research.public_market_data_v1 import (
    EXCHANGE_FACTORIES,
    CcxtPublicBookTransportV1,
)


def test_transport_exposes_only_allowlisted_public_book_read(monkeypatch) -> None:
    fake = FakePublicExchange()
    monkeypatch.setitem(EXCHANGE_FACTORIES, "binanceusdm", lambda config: fake)
    transport = CcxtPublicBookTransportV1("binanceusdm")

    book = transport.fetch_order_book("BTC/USDT:USDT", limit=20)

    assert fake.calls == [("fetch_order_book", "BTC/USDT:USDT", 20)]
    assert book["nonce"] == 101
    assert not hasattr(transport, "request")
    assert not hasattr(transport, "create_order")


@pytest.mark.parametrize(
    "venue,instrument,limit",
    [
        ("unknown", "BTC/USDT:USDT", 20),
        ("binanceusdm", "../private/order", 20),
        ("binanceusdm", "BTC/USDT:USDT", 100),
    ],
)
def test_transport_rejects_unknown_dynamic_or_non_allowlisted_inputs(venue, instrument, limit) -> None:
    with pytest.raises(ValueError):
        CcxtPublicBookTransportV1(venue).fetch_order_book(instrument, limit=limit)
```

The fake exchange defines mutation methods that raise `AssertionError`; assert none are called. The production adapter accepts venue `binanceusdm`, a CCXT unified symbol matching `^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$`, and limit in `{5, 10, 20}` only. It constructs CCXT with exactly `{"enableRateLimit": True}` and no credential fields.

- [ ] **Step 2: Implement the narrow adapter**

```python
"""Allowlisted public order-book transport; no generic request surface."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol

import ccxt


class PublicBookTransportV1(Protocol):
    def fetch_order_book(self, instrument_id: str, *, limit: int) -> Mapping[str, Any]:
        raise NotImplementedError


EXCHANGE_FACTORIES = {"binanceusdm": ccxt.binanceusdm}
_INSTRUMENT = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$")


class CcxtPublicBookTransportV1:
    def __init__(self, venue: str) -> None:
        if venue not in EXCHANGE_FACTORIES:
            raise ValueError("venue is not allowlisted")
        self.venue = venue
        self._exchange = EXCHANGE_FACTORIES[venue]({"enableRateLimit": True})

    def fetch_order_book(self, instrument_id: str, *, limit: int) -> Mapping[str, Any]:
        if not _INSTRUMENT.fullmatch(instrument_id) or limit not in {5, 10, 20}:
            raise ValueError("public order-book request is not allowlisted")
        return self._exchange.fetch_order_book(instrument_id, limit=limit)
```

No method delegates arbitrary method names, paths, HTTP verbs, auth parameters, or exchange `request`.

- [ ] **Step 3: Update capture semantics tests**

`capture_public_order_book` remains a metadata capture helper. It must:

- call only `PublicBookTransportV1.fetch_order_book`;
- stamp `source_available_at == captured_at` after fetch;
- preserve exchange `timestamp`, `nonce`, bids, and asks;
- reject missing/null exchange timestamp or nonce rather than fabricate exchange time;
- return a plain captured mapping consumed by `build_execution_observation`.

Keep the existing after-fetch clock test and add missing timestamp/nonce rejection.

- [ ] **Step 4: Update CLI arguments and freeze behavior**

The CLI arguments become:

```text
--runtime-dir
--execution-freeze
--expected-execution-freeze-sha256
--a1
--public-market-data
--venue
--symbol
--book-limit
```

Rules:

- `--execution-freeze` and expected hash are required for any decision;
- `--a1` always exits with `A1 remains disabled; B1 is engineering-only`;
- default mode uses one deterministic synthetic book and explicit timestamps;
- public mode uses `CcxtPublicBookTransportV1`, captures the book, then stamps decision/execution time and builds one observation;
- build the intent from the verified freeze's manifest ID/candidate hash plus `requested_exposure="0.1"`, `requested_notional_quote="100"`, `nav_before_quote="1000"`, `side="buy"`, and `signal="0.25"`;
- process through `PaperRuntimeV9`; print only IDs/status/evidence class.

- [ ] **Step 5: Strengthen safety tests**

Keep existing AST scans and expand the production file set to the new transport/observation modules and paper script. Add `borrow` and `repay` to forbidden calls. Assert the only exchange call in `public_market_data_v1.py` is `fetch_order_book`; reject attribute calls to `request`, `fetch2`, private API groups, any mutation name, or a dynamically computed method via `getattr`.

- [ ] **Step 6: Run tests and commit**

```bash
python -m pytest -q tests/test_public_market_data_v1.py tests/test_paper_v9.py tests/test_v8_live_order_safety.py
ruff check src tests scripts
python -m compileall -q src tests scripts
git diff --check
git add src/crypto_research/public_market_data_v1.py src/crypto_research/paper_v9.py scripts/run_v9_paper.py tests/test_public_market_data_v1.py tests/test_paper_v9.py tests/test_v8_live_order_safety.py
git commit -m "feat: restrict paper market data to public reads"
```

### Task 7: B1 acceptance and integration verification

**Files:**
- No source changes unless a test exposes a root-cause defect; any correction repeats the focused red/green cycle and receives its own commit.
- Create a new `paper_readiness_versions/version_*` checkpoint only after Lane A and B1 both satisfy their approved acceptance criteria.

**Interfaces:**
- Consumes: all B1 tasks plus foundation.
- Produces: green focused/full checks, deterministic replay evidence, clean branch, unchanged recorders, and no paper/A1/live authorization.

- [ ] **Step 1: Run B1 focused suites**

```bash
python -m pytest -q \
  tests/test_canonical_json.py \
  tests/test_execution_observation_v1.py \
  tests/test_point_in_time_v8.py \
  tests/test_execution_v8.py \
  tests/test_v9_governance.py \
  tests/test_shadow_paper_v8.py \
  tests/test_paper_v9.py \
  tests/test_public_market_data_v1.py \
  tests/test_v8_live_order_safety.py
```

Expected: all tests pass.

- [ ] **Step 2: Run the complete repository contract**

```bash
python -m pytest -q
ruff check src tests scripts
python -m compileall -q src tests scripts
python -m json.tool configs/v9_engineering_execution_freeze_v1.json >/dev/null
git diff --check
git status --short
```

Expected: all checks pass and the worktree is clean.

- [ ] **Step 3: Run the offline engineering smoke only**

```bash
python scripts/run_v9_paper.py \
  --runtime-dir /tmp/investment-b1-engineering-smoke \
  --execution-freeze configs/v9_engineering_execution_freeze_v1.json \
  --expected-execution-freeze-sha256 "$(tr -d '\n' < configs/v9_engineering_execution_freeze_v1.json.sha256)"
```

Expected: one `ENGINEERING_ONLY` simulated decision with explicit execution status. Do not pass `--a1` or `--public-market-data` for acceptance.

- [ ] **Step 4: Re-run from a fresh temporary runtime and compare hashes**

Use two newly created explicit directories under `/tmp`, run the same fixed offline replay in each, and compare the decision/fill/journal hashes printed or persisted. They must match byte-for-byte. Delete only those two newly created temporary directories after resolving their exact paths; do not use a broad recursive target or environment-variable path.

- [ ] **Step 5: Verify invariant state**

Confirm read-only that:

- V17 remains `COLLECTING`;
- trial 871 remains unauthorized and unconsumed;
- candidate remains unfrozen;
- `READY_TO_START_PAPER=false`;
- `A1=NOT_STARTED`;
- `LIVE_NOT_AUTHORIZED`;
- L2 and positioning recorder processes remain running and their source/config/data were not modified.
