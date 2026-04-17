"""
One-command local smoke test for the Alpha Engine.

Runs a single bounded round of the orchestrator (ALPHA_MAX_ROUNDS=1)
against the current LM Studio endpoint, then runs both inspectors:
- inspect_state_tracker.py
- inspect_alpha_concepts.py --limit 5

This script is for manual use only; it does not change runtime behavior.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded Alpha Engine smoke test against LM Studio.")
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="LM Studio model ID to use for this smoke run (sets ALPHA_MODEL_ID for the orchestrator subprocess only).",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Number of rounds to run (sets ALPHA_MAX_ROUNDS for the orchestrator subprocess; default: 1).",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    rounds = args.rounds if args.rounds > 0 else 1
    env["ALPHA_MAX_ROUNDS"] = str(rounds)
    if args.model:
        env["ALPHA_MODEL_ID"] = args.model

    orchestrator_cmd = [
        sys.executable,
        str(ROOT / "orchestrator.py"),
        "Design a US-compliant, mid-frequency trading execution framework that rigorously attacks slippage and fee assumptions in US markets",
    ]

    print(f">>> Running orchestrator for {rounds} round(s) (ALPHA_MAX_ROUNDS={rounds})...")
    if args.model:
        print(f"    Using ALPHA_MODEL_ID={args.model}")
    subprocess.run(orchestrator_cmd, env=env, check=False)

    print("\n>>> Running inspect_state_tracker.py (first 10 rows)...")
    subprocess.run([sys.executable, str(ROOT / "inspect_state_tracker.py")], check=False)

    print("\n>>> Running inspect_alpha_concepts.py --limit 5...")
    subprocess.run(
        [sys.executable, str(ROOT / "inspect_alpha_concepts.py"), "--limit", "5"],
        check=False,
    )


if __name__ == "__main__":
    main()


