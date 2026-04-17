"""
Manual Alpha Engine memory query helper.

Queries the isolated Alpha-only BM25 and Qdrant indices built from alpha_concepts_chunks.jsonl.

This helper is MANUAL/OPT-IN and does NOT modify live retrieval or router behavior.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from config import get_config
from index_bm25 import BM25Index
from index_qdrant import QdrantIndex, EmbeddingModel


def load_alpha_bm25(data_dir: Path) -> BM25Index:
    index_path = data_dir / "bm25_alpha_index.pkl"
    if not index_path.exists():
        raise FileNotFoundError(f"Alpha BM25 index not found at {index_path}")
    return BM25Index.load(index_path)


def load_alpha_qdrant(qdrant_dir: Path, model_name: str) -> tuple[QdrantIndex, EmbeddingModel]:
    collection = "alpha_engine_children"
    embed_model = EmbeddingModel(model_name=model_name)
    index = QdrantIndex(
        qdrant_path=qdrant_dir,
        collection_name=collection,
        embedding_dim=embed_model.dimension,
    )
    return index, embed_model


def _round_from_parent_id(parent_id: str) -> str:
    """Derive round label from Alpha parent_id e.g. alpha_parent_1 -> 1."""
    if not parent_id:
        return "?"
    if parent_id.startswith("alpha_parent_"):
        return parent_id.replace("alpha_parent_", "", 1)
    return parent_id


def get_alpha_self_memory_context(query: str, top_k: int = 3) -> str:
    """
    Query isolated Alpha BM25 + Qdrant and return a compact context string for
    injection into RAG context. Returns "" if Alpha artifacts missing or on error.
    Used by orchestrator when ALPHA_USE_SELF_MEMORY=1.
    Paths: data_dir/bm25_alpha_index.pkl, data_dir/qdrant_alpha, collection alpha_engine_children.
    """
    if not (query or "").strip():
        return ""
    try:
        cfg = get_config()
        data_dir = cfg.paths.data_dir
        qdrant_alpha_dir = data_dir / "qdrant_alpha"
        bm25_path = data_dir / "bm25_alpha_index.pkl"
        if not bm25_path.exists() or not qdrant_alpha_dir.exists():
            return ""
        bm25 = BM25Index.load(bm25_path)
        qdrant_index, embed_model = load_alpha_qdrant(qdrant_alpha_dir, cfg.embedding.model)
        bm25_hits = bm25.search(query.strip(), top_k=top_k)
        q_vec = embed_model.embed_single(query.strip())
        vec_hits = qdrant_index.search(q_vec, top_k=top_k)
        scores = {}
        for cid, s in bm25_hits:
            scores.setdefault(cid, {"bm25": 0.0, "vec": 0.0})
            scores[cid]["bm25"] = float(s)
        for cid, s in vec_hits:
            scores.setdefault(cid, {"bm25": 0.0, "vec": 0.0})
            scores[cid]["vec"] = float(s)
        merged = []
        for cid, sc in scores.items():
            merged.append((cid, sc["bm25"] + sc["vec"]))
        merged.sort(key=lambda x: x[1], reverse=True)
        merged = merged[:top_k]
        parts = []
        for i, (cid, _) in enumerate(merged, 1):
            preview = bm25._chunk_texts.get(cid, "").replace("\n", " ").strip()
            if not preview:
                preview = "(Alpha chunk)"
            parts.append(f"[{i}] {preview[:400]}")
        return "\n\n".join(parts) if parts else ""
    except Exception:
        return ""


def query_alpha_memory(query: str, top_k: int = 5, show_meta: bool = False) -> None:
    cfg = get_config()
    data_dir = cfg.paths.data_dir
    qdrant_alpha_dir = data_dir / "qdrant_alpha"

    print(f"Alpha query: {query!r}")
    print(f"Data dir: {data_dir}")
    print(f"Qdrant Alpha dir: {qdrant_alpha_dir}")

    # Load BM25 and Qdrant Alpha-only indices
    bm25 = load_alpha_bm25(data_dir)
    qdrant_index, embed_model = load_alpha_qdrant(qdrant_alpha_dir, cfg.embedding.model)

    # BM25 search
    bm25_hits = bm25.search(query, top_k=top_k)

    # Vector search (Alpha Qdrant)
    q_vec = embed_model.embed_single(query)
    vec_hits = qdrant_index.search(q_vec, top_k=top_k)

    # Merge by chunk_id with simple additive score (bm25 + vector)
    scores = {}
    for cid, s in bm25_hits:
        scores.setdefault(cid, {"bm25": 0.0, "vec": 0.0})
        scores[cid]["bm25"] = float(s)
    for cid, s in vec_hits:
        scores.setdefault(cid, {"bm25": 0.0, "vec": 0.0})
        scores[cid]["vec"] = float(s)

    merged = []
    for cid, sc in scores.items():
        merged.append((cid, sc["bm25"], sc["vec"], sc["bm25"] + sc["vec"]))

    merged.sort(key=lambda x: x[3], reverse=True)
    merged = merged[:top_k]

    # Fetch texts for display from BM25 index's stored chunk_texts if available
    print("\nTop Alpha-memory hits:")
    if not merged:
        print("  (no hits)")
        return

    for rank, (cid, bm25_s, vec_s, total_s) in enumerate(merged, 1):
        preview = bm25._chunk_texts.get(cid, "")[:200].replace("\n", " ")
        print(f"{rank}. chunk_id={cid}")
        print(f"   bm25={bm25_s:.4f} vec={vec_s:.4f} total={total_s:.4f}")
        if preview:
            print(f"   text~ {preview}...")
        else:
            print("   text~ <not cached in BM25 index>")
        if show_meta:
            pt = qdrant_index.get_point(cid)
            if pt and isinstance(pt.get("payload"), dict):
                p = pt["payload"]
                round_label = _round_from_parent_id(p.get("parent_id") or "")
                sections = p.get("section_headers") or []
                doc_id = p.get("doc_id") or ""
                parent_id = p.get("parent_id") or ""
                source = (p.get("source_path") or "")[:80]
                print(f"   meta: round={round_label} doc_id={doc_id} parent_id={parent_id}")
                if sections:
                    print(f"   sections: {sections}")
                if source:
                    print(f"   source: {source}")
            else:
                print("   meta: (no Qdrant payload)")


def main() -> None:
    try:
        from repo_paths import ensure_rag_v2_base_dir_env
    except ImportError:
        from .repo_paths import ensure_rag_v2_base_dir_env

    ensure_rag_v2_base_dir_env()
    parser = argparse.ArgumentParser(description="Query isolated Alpha Engine memory indices.")
    parser.add_argument("query", type=str, help="Alpha-memory query string")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to show")
    parser.add_argument(
        "--show-meta",
        action="store_true",
        help="Print round/section/source metadata for each hit (from Qdrant payload).",
    )
    args = parser.parse_args()

    query_alpha_memory(args.query, top_k=args.top_k, show_meta=args.show_meta)


if __name__ == "__main__":
    main()

