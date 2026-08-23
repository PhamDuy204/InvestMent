"""Run the V9 four-role Qwen research council and persist only final structured output."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from groq import Groq

from crypto_research.groq_v9 import run_v9_research_council


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deterministic-allow-test", action="store_true")
    args = parser.parse_args()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required at runtime")
    context = json.loads(args.context.read_text(encoding="utf-8"))
    result = run_v9_research_council(
        context,
        client=Groq(api_key=api_key),
        deterministic_allow_test=args.deterministic_allow_test,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"model": result["model"], "effective_decision": result["effective_decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
