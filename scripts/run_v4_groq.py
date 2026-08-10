from __future__ import annotations

import argparse
import json
from pathlib import Path

from groq import Groq

from crypto_research.groq_v4 import resolve_available_routes
from crypto_research.v4_research import run_v4_research


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the V4 research-only Groq ensemble")
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/v4_groq"))
    args = parser.parse_args()

    context = json.loads(args.context.read_text())
    client = Groq()
    routes = resolve_available_routes(client)
    result = run_v4_research(
        client,
        context,
        artifact_dir=args.artifact_dir,
        model_routes=routes,
    )
    print(json.dumps({"status": result["status"], "models": result["models"]}, indent=2))
    for index, hypothesis in enumerate(result["ranked_hypotheses"], start=1):
        print(f"{index}. {hypothesis['name']} [{hypothesis['experiment_family']}]")


if __name__ == "__main__":
    main()
