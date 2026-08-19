from __future__ import annotations

import json
import os
from pathlib import Path

from groq import Groq

from crypto_research.groq_v7 import run_v7_research_council

ROOT = Path("artifacts/multi_asset_v7")


def main() -> None:
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not available to the V7 research workflow")
    context = json.loads((ROOT / "research_council_context.json").read_text(encoding="utf-8"))
    blocked = {str(item) for item in context.get("blocked_fingerprints", [])}
    result = run_v7_research_council(context, client=Groq(), blocked_fingerprints=blocked)
    output = ROOT / "groq_council_output.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "role_models": result.get("role_models"),
                "approved_hypothesis_ids": [
                    item.get("hypothesis_id")
                    for item in result.get("approved_hypotheses", [])
                    if isinstance(item, dict)
                ],
                "locally_rejected_count": len(result.get("locally_rejected_hypotheses", [])),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
