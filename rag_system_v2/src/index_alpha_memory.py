"""
Build isolated Alpha Engine memory indices from alpha_concepts_chunks.jsonl.

This helper is MANUAL/OPT-IN and does NOT modify the live RAG indices or retrieval path.

It:
- Reads alpha_concepts_chunks.jsonl from config.paths.data_dir
- Builds a dedicated BM25 index (bm25_alpha_index.pkl)
- Builds a dedicated Qdrant collection (alpha_engine_children) under the existing qdrant_dir
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from config import get_config
from index_bm25 import build_bm25_from_jsonl
from index_qdrant import build_qdrant_index

try:
    from repo_paths import ensure_rag_v2_base_dir_env
except ImportError:
    from .repo_paths import ensure_rag_v2_base_dir_env

ensure_rag_v2_base_dir_env()

ALPHA_COLLECTION = "alpha_engine_children"


def _recreate_alpha_collection(qdrant_dir: Path) -> None:
    """Delete only the isolated Alpha collection so the next build starts clean."""
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        raise ImportError("qdrant-client required. Run: pip install qdrant-client")
    client = QdrantClient(path=str(qdrant_dir))
    try:
        collections = client.get_collections().collections
        names = [c.name for c in collections]
        if ALPHA_COLLECTION in names:
            client.delete_collection(ALPHA_COLLECTION)
            logging.getLogger(__name__).info(f"Deleted collection {ALPHA_COLLECTION} for rebuild")
        else:
            logging.getLogger(__name__).info(f"Collection {ALPHA_COLLECTION} not present, skipping delete")
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build isolated Alpha Engine memory indices (BM25 + Qdrant)."
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and rebuild only the Alpha Qdrant collection (alpha_engine_children) before indexing.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = get_config()
    data_dir = config.paths.data_dir
    qdrant_alpha_dir = data_dir / "qdrant_alpha"

    alpha_chunks = data_dir / "alpha_concepts_chunks.jsonl"
    if not alpha_chunks.exists():
        print(f"alpha_concepts_chunks.jsonl not found at {alpha_chunks}")
        print("Run prepare_alpha_memory.py first to generate Alpha chunks.")
        return

    # ----------------------------------------------------------------------
    # BM25: build isolated Alpha-memory index
    # ----------------------------------------------------------------------
    bm25_alpha_path = data_dir / "bm25_alpha_index.pkl"
    print(f"Building Alpha BM25 index from {alpha_chunks} -> {bm25_alpha_path}")
    bm25_index = build_bm25_from_jsonl(
        chunks_path=alpha_chunks,
        output_path=bm25_alpha_path,
        k1=config.bm25.k1,
        b=config.bm25.b,
    )
    bm25_stats = bm25_index.get_stats()
    print(
        f"[OK] Alpha BM25 index built: {bm25_stats['total_docs']} docs, "
        f"{bm25_stats['total_terms']} terms"
    )
    print(f"  Saved to: {bm25_alpha_path}")

    # ----------------------------------------------------------------------
    # Qdrant: build isolated Alpha-memory collection
    # ----------------------------------------------------------------------
    if args.recreate:
        _recreate_alpha_collection(qdrant_alpha_dir)

    alpha_cache_dir = data_dir / "embedding_cache_alpha"
    alpha_cache_dir.mkdir(parents=True, exist_ok=True)
    qdrant_alpha_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Building Alpha Qdrant index from {alpha_chunks} into "
        f"collection '{ALPHA_COLLECTION}' at {qdrant_alpha_dir}"
    )
    qdrant_index = build_qdrant_index(
        chunks_path=alpha_chunks,
        qdrant_path=qdrant_alpha_dir,
        model_name=config.embedding.model,
        collection_name=ALPHA_COLLECTION,
        cache_dir=alpha_cache_dir,
        batch_size=config.embedding.batch_size,
    )

    count = qdrant_index.count()
    print(f"[OK] Alpha Qdrant index built: {count} vectors")
    print(f"  Stored at: {qdrant_alpha_dir} (collection: {ALPHA_COLLECTION})")


if __name__ == "__main__":
    main()

