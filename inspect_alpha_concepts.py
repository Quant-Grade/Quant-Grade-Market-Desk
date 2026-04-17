"""
Read-only diagnostic for rag_system_v2/data/alpha_concepts.jsonl.

Validates core keys per record and prints a compact summary of recent entries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ALPHA_PATH = ROOT / "rag_system_v2" / "data" / "alpha_concepts.jsonl"

REQUIRED_KEYS = [
    "round",
    "timestamp",
    "current_task",
    "builder_expansion",
    "query_memory_for",
    "compressor_summary",
    "redteam_attacks",
    "leader_next_task",
    "state_tracker",
]


def iter_records(path: Path):
    if not path.exists():
        print(f"alpha_concepts.jsonl not found at {path}")
        return

    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    yield idx, obj, None
                else:
                    yield idx, None, "not_a_dict"
            except Exception as e:
                yield idx, None, f"invalid_json: {e.__class__.__name__}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect alpha_concepts.jsonl records.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of most recent records to show (default: 10).",
    )
    args = parser.parse_args()

    if not ALPHA_PATH.exists():
        print(f"alpha_concepts.jsonl not found at {ALPHA_PATH}")
        return

    records = list(iter_records(ALPHA_PATH))
    if not records:
        print("No records found in alpha_concepts.jsonl")
        return

    # Show only the last N records
    tail = records[-args.limit :] if args.limit > 0 else records

    print("line | status       | round | current_task | baton_next_task")
    print("---- | ------------ | ----- | ------------ | ----------------")

    for line_no, obj, err in tail:
        if err is not None or obj is None:
            print(f"{line_no:4d} | {err or 'invalid'} |  -   |  | ")
            continue

        missing = [k for k in REQUIRED_KEYS if k not in obj]
        if missing:
            status = "missing:" + ",".join(missing)
        else:
            status = "ok"

        rnd = obj.get("round")
        task = str(obj.get("current_task", "") or "")
        baton = str(obj.get("leader_next_task", "") or "")

        task_s = (task[:24] + "…") if len(task) > 24 else task
        baton_s = (baton[:24] + "…") if len(baton) > 24 else baton

        print(f"{line_no:4d} | {status:12s} | {str(rnd):5s} | {task_s} | {baton_s}")


if __name__ == "__main__":
    main()

