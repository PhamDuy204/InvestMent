# Shared Strict Provenance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one strict standard-library canonical serialization/hash contract for both approved lanes and ensure CI checks every script.

**Architecture:** Add one pure module that converts supported values into deterministic JSON-compatible values, prefixes a versioned hash domain, and rejects ambiguous timestamps, non-finite numbers, unsupported types, and non-string mapping keys. Lane A and B1 consume this module; existing loose historical serializers remain unchanged.

**Tech Stack:** Python 3.11 standard library (`datetime`, `decimal`, `hashlib`, `json`), pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-24-paper-readiness-and-multi-market-design.md`

## Global Constraints

- No new dependency.
- Do not modify V32 history, recorders, recorder data, trial state, candidate state, paper state, or outcome data.
- Canonical timestamps are UTC RFC 3339 with exactly six fractional digits and suffix `Z`.
- Booleans remain booleans; integers remain integers; non-integer finite numbers become canonical base-10 strings; negative zero becomes `"0"`.
- Canonical bytes are `domain.encode("utf-8") + b"\\0" + normalized_json`.
- JSON uses UTF-8, sorted keys, `(",", ":")` separators, and `ensure_ascii=False`.
- Unsupported values, non-string mapping keys, naive timestamps, NaN, and infinity fail closed.
- `LIVE_NOT_AUTHORIZED` remains invariant.

## Execution Environment

Before Task 1, from the repository root, create/reuse the ignored repo-local environment and activate it:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
source .venv/bin/activate
python -c 'import pandas, pyarrow, pytest; print("development environment ready")'
```

Every fresh implementation agent must run `source .venv/bin/activate` before the task's commands. Do not commit `.venv`, a lockfile generated only by environment setup, or dependency changes.

---

### Task 1: Strict canonical JSON and SHA-256

**Files:**
- Create: `src/crypto_research/canonical_json.py`
- Create: `tests/test_canonical_json.py`

**Interfaces:**
- Consumes: Python scalar/container values; callers pre-normalize repository-relative paths to POSIX strings.
- Produces: `canonical_utc(value, *, field) -> str`, `canonical_decimal(value, *, field) -> str`, `canonical_bytes(domain, payload) -> bytes`, and `canonical_sha256(domain, payload) -> str`.

- [ ] **Step 1: Write the failing timestamp and numeric tests**

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from crypto_research.canonical_json import (
    canonical_bytes,
    canonical_decimal,
    canonical_sha256,
    canonical_utc,
)


def test_canonical_timestamp_and_decimal_are_unambiguous() -> None:
    assert canonical_utc(
        datetime(2026, 8, 24, 6, 0, 0, 1, tzinfo=timezone.utc),
        field="captured_at",
    ) == "2026-08-24T06:00:00.000001Z"
    assert canonical_utc("2026-08-24T13:00:00+07:00", field="captured_at") == (
        "2026-08-24T06:00:00.000000Z"
    )
    assert canonical_decimal(Decimal("100.5000"), field="price") == "100.5"
    assert canonical_decimal(-0.0, field="quantity") == "0"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_decimal_rejects_non_finite(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_decimal(value, field="price")


def test_canonical_utc_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_utc(datetime(2026, 8, 24, 6), field="captured_at")
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run:

```bash
python -m pytest -q tests/test_canonical_json.py
```

Expected: collection fails with `ModuleNotFoundError: crypto_research.canonical_json`.

- [ ] **Step 3: Add deterministic-byte and strict-type tests**

```python
def test_canonical_bytes_are_order_independent_and_domain_separated() -> None:
    left = {"b": 2, "a": 1.25, "when": "2026-08-24T06:00:00.000000Z"}
    right = {"when": "2026-08-24T06:00:00.000000Z", "a": 1.2500, "b": 2}

    assert canonical_bytes("gate-v1", left) == canonical_bytes("gate-v1", right)
    assert canonical_sha256("gate-v1", left) == canonical_sha256("gate-v1", right)
    assert canonical_sha256("gate-v1", left) != canonical_sha256("book-v1", left)
    assert canonical_bytes("gate-v1", left).startswith(b"gate-v1\0")


@pytest.mark.parametrize(
    "payload",
    [
        {1: "non-string-key"},
        {"unsupported": object()},
        {"path": __import__("pathlib").Path("/absolute/path")},
    ],
)
def test_canonical_bytes_reject_unsupported_or_ambiguous_values(payload) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_bytes("gate-v1", payload)
```

- [ ] **Step 4: Implement the minimal strict serializer**

```python
"""Strict canonical JSON used by new prospective and paper provenance only."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def canonical_utc(value: datetime | str, *, field: str) -> str:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_decimal(value: Decimal | float | int | str, *, field: str) -> str:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric, not bool")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a base-10 number") from exc
    if not decimal.is_finite():
        raise ValueError(f"{field} must be finite")
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _normalized(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, (Decimal, float)):
        return canonical_decimal(value, field="value")
    if isinstance(value, datetime):
        return canonical_utc(value, field="value")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical mapping keys must be strings")
        return {key: _normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_bytes(domain: str, payload: Mapping[str, Any]) -> bytes:
    if not domain or "\x00" in domain:
        raise ValueError("domain must be non-empty and contain no NUL")
    normalized = json.dumps(
        _normalized(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return domain.encode("utf-8") + b"\0" + normalized


def canonical_sha256(domain: str, payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(domain, payload)).hexdigest()
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python -m pytest -q tests/test_canonical_json.py
```

Expected: all tests pass.

- [ ] **Step 6: Run static checks for the new files**

Run:

```bash
ruff check src/crypto_research/canonical_json.py tests/test_canonical_json.py
python -m compileall -q src/crypto_research/canonical_json.py tests/test_canonical_json.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit the foundation**

```bash
git add src/crypto_research/canonical_json.py tests/test_canonical_json.py
git commit -m "feat: add strict provenance canonicalization"
```

### Task 2: Make CI lint every script

**Files:**
- Modify: `.github/workflows/ci.yml:32`

**Interfaces:**
- Consumes: existing CI Python environment.
- Produces: one repository-wide Ruff invocation covering all current and future scripts.

- [ ] **Step 1: Verify the current selective lint command**

Run:

```bash
grep -n "ruff check" .github/workflows/ci.yml
```

Expected: the command names only `src`, `tests`, and two scripts.

- [ ] **Step 2: Replace the selective command**

Replace:

```yaml
      - run: ruff check src tests scripts/build_v8_execution_panel.py scripts/run_v8_h8_execution_fragility.py
```

with:

```yaml
      - run: ruff check src tests scripts
```

- [ ] **Step 3: Run the exact expanded check**

Run:

```bash
ruff check src tests scripts
python -m compileall -q src tests scripts
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit the CI scope correction**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint all research scripts"
```

### Task 3: Foundation verification checkpoint

**Files:**
- No source changes.

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: a clean foundation commit from which Lane A and B1 can branch into isolated work.

- [ ] **Step 1: Run the focused and full checks**

```bash
python -m pytest -q tests/test_canonical_json.py
python -m pytest -q
ruff check src tests scripts
python -m compileall -q src tests scripts
git diff --check
git status --short
```

Expected: tests/static checks pass and the worktree is clean.

- [ ] **Step 2: Record the dependency boundary**

Lane A may import only `canonical_bytes`, `canonical_sha256`, `canonical_utc`, and `canonical_decimal` from the new module. B1 may import the same four functions. Neither lane edits this module concurrently; any correction is integrator-owned and lands before dependent commits.
