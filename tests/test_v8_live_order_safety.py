from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_CALLS = {
    "new_order",
    "create_order",
    "place_order",
    "cancel_order",
    "withdraw",
    "transfer",
    "change_leverage",
    "set_leverage",
}


def test_v8_source_has_no_executable_live_order_calls() -> None:
    root = Path("src/crypto_research")
    violations: list[str] = []
    for path in root.glob("*v8.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
            if name in FORBIDDEN_CALLS:
                violations.append(f"{path}:{node.lineno}:{name}")
    assert not violations, "live-trading calls found: " + ", ".join(violations)
