"""
One-command Alpha memory preparation helper.

Steps:
1. Convert alpha_concepts.jsonl -> alpha_concepts_chunks.jsonl (RAG-ready ChildChunk schema)
2. Validate alpha_concepts_chunks.jsonl using the same checks as doctor.check_alpha_concepts_chunks_jsonl

This script is manual/opt-in and does NOT modify indices or retrieval behavior.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

try:
    from repo_paths import ensure_rag_v2_base_dir_env
except ImportError:
    from .repo_paths import ensure_rag_v2_base_dir_env

ensure_rag_v2_base_dir_env()


def convert_alpha_concepts() -> None:
    # Reuse existing converter; it will pick up RAG_V2_BASE_DIR set above.
    from ingest_alpha_concepts import main as convert_main

    convert_main()


def validate_alpha_chunks() -> None:
    # Mirror doctor.check_alpha_concepts_chunks_jsonl logic without package import friction
    from config import get_config

    config = get_config()
    chunks_path = config.paths.data_dir / "alpha_concepts_chunks.jsonl"

    if not chunks_path.exists():
        print(f"alpha_concepts_chunks.jsonl not found at {chunks_path}")
        return

    count = 0
    chunk_ids = []
    issues = []

    try:
        with chunks_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    count += 1

                    if "chunk_id" not in chunk:
                        issues.append(f"Line {i}: missing chunk_id")
                    else:
                        chunk_ids.append(chunk["chunk_id"])

                    if "text_original" not in chunk and "text" not in chunk:
                        issues.append(f"Line {i}: missing text_original/text")

                    if "schema_version" in chunk and chunk["schema_version"] != 2:
                        issues.append(f"Line {i}: wrong schema version")
                except json.JSONDecodeError as e:
                    issues.append(f"Line {i}: invalid JSON - {e}")
    except Exception as e:
        print(f"Failed to read alpha_concepts_chunks.jsonl: {e}")
        return

    id_counts = Counter(chunk_ids)
    duplicates = [cid for cid, cnt in id_counts.items() if cnt > 1]
    if duplicates:
        issues.append(f"Duplicate chunk_ids: {len(duplicates)}")

    print(f"Total Alpha chunks: {count}")
    print(f"Unique Alpha IDs: {len(set(chunk_ids))}")

    if issues:
        status = "FAIL" if len(issues) >= 5 else "WARN"
        print(f"[{status}] {len(issues)} issues found in alpha_concepts_chunks.jsonl")
        for msg in issues[:10]:
            print(f"  - {msg}")
        if duplicates:
            print(f"  (First {min(5,len(duplicates))} duplicate IDs): {duplicates[:5]}")
    else:
        print("[PASS] alpha_concepts_chunks.jsonl: all records valid")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare Alpha-memory chunks (convert + validate) or introspect base paths."
    )
    parser.add_argument(
        "--print-base",
        action="store_true",
        help="Print resolved RAG base and data dir, then exit without converting or validating.",
    )
    args = parser.parse_args()

    if args.print_base:
        from config import get_config

        config = get_config()
        print(f"RAG_V2_BASE_DIR: {os.environ.get('RAG_V2_BASE_DIR')}")
        print(f"config.paths.data_dir: {config.paths.data_dir}")
        return

    print(">>> Converting alpha_concepts.jsonl to alpha_concepts_chunks.jsonl...")
    convert_alpha_concepts()

    print("\n>>> Validating alpha_concepts_chunks.jsonl...")
    validate_alpha_chunks()


if __name__ == "__main__":
    main()

