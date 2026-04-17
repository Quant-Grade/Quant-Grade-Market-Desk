"""
Convert Alpha Engine self-memory (alpha_concepts.jsonl) into RAG-ready chunks JSONL.

This utility is read-only with respect to live indices. It:
- Reads rag_system_v2/data/alpha_concepts.jsonl
- Converts each round record into one or more ChildChunk-like dicts
- Writes them to rag_system_v2/data/alpha_concepts_chunks.jsonl

No Qdrant/BM25/index updates are performed here.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Dict


ROOT = Path(__file__).resolve().parent


def _stable_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _alpha_round_to_text(record: Dict) -> str:
    """Build a single text field from an alpha_concepts record."""
    parts = []
    r = record
    parts.append(f"Round {r.get('round')}: {r.get('current_task','')}")
    be = (r.get("builder_expansion") or "").strip()
    if be:
        parts.append("\n\n[Builder]\n" + be)
    cs = (r.get("compressor_summary") or "").strip()
    if cs:
        parts.append("\n\n[Compressor]\n" + cs)
    rt = (r.get("redteam_attacks") or "").strip()
    if rt:
        parts.append("\n\n[RedTeam]\n" + rt)
    ln = (r.get("leader_next_task") or "").strip()
    if ln:
        parts.append("\n\n[Leader Next Task]\n" + ln)
    st = r.get("state_tracker") or {}
    if isinstance(st, dict) and st:
        parts.append("\n\n[State Tracker]\n" + json.dumps(st, ensure_ascii=False, indent=2))
    return "".join(parts).strip()


def main() -> None:
    from ingest import ChildChunk, FileType  # reuse existing schema
    from config import get_config

    # Resolve data directory from existing RAG config
    config = get_config()
    data_dir = config.paths.data_dir
    alpha_input = data_dir / "alpha_concepts.jsonl"
    alpha_chunks_output = data_dir / "alpha_concepts_chunks.jsonl"

    if not alpha_input.exists():
        print(f"alpha_concepts.jsonl not found at {alpha_input}")
        return

    data_dir.mkdir(parents=True, exist_ok=True)

    out_path = alpha_chunks_output
    count = 0

    with alpha_input.open("r", encoding="utf-8") as f_in, out_path.open("w", encoding="utf-8") as f_out:
        for i, line in enumerate(f_in, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
                if not isinstance(rec, dict):
                    print(f"Skipping line {i}: not a JSON object")
                    continue
            except Exception as e:
                print(f"Skipping line {i}: invalid JSON ({e.__class__.__name__})")
                continue

            # Build a synthetic doc_id and parent_id for Alpha Engine memory
            doc_id = f"alpha_engine_memory"
            text = _alpha_round_to_text(rec)
            if not text:
                continue

            round_no = rec.get("round")
            parent_id = f"alpha_parent_{round_no}"
            child_index = 0

            chunk_hash = _stable_hash(text)
            # Include chunk_hash so same round + different content get distinct chunk_ids (deterministic per record).
            chunk_id = _stable_hash(f"{doc_id}:{parent_id}:{child_index}:{chunk_hash}")

            chunk = ChildChunk(
                chunk_id=chunk_id,
                chunk_hash=chunk_hash,
                doc_id=doc_id,
                parent_id=parent_id,
                child_index=child_index,
                text_original=text,
                text_normalized=text,
                char_start=0,
                char_end=len(text),
                source_path=str(alpha_input),
                file_type=FileType.TEXT.value,
                page_num=None,
                section_headers=[f"AlphaEngine Round {round_no}"],
            )

            chunk_dict = asdict(chunk)
            chunk_dict["schema_version"] = 2  # Align with SCHEMA_VERSION used in main ingest
            f_out.write(json.dumps(chunk_dict, ensure_ascii=False) + "\n")
            count += 1

    print(f"Wrote {count} alpha_concepts chunks to {out_path}")


if __name__ == "__main__":
    main()

