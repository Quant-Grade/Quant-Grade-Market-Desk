"""
Single source of truth for rag_system_v2 on-disk layout (portable, clone-relative).

Resolution order for the RAG v2 install root (``base_dir`` / ``RAG_V2_BASE_DIR``):
1. Environment variable ``RAG_V2_BASE_DIR`` (if set), ``expanduser()`` + ``resolve()``.
2. Else: directory that contains this ``src/`` folder (the ``rag_system_v2`` package root).

Artifact filenames used across ingest, retrieve, doctor, and manifest verification
must stay aligned here to avoid silent path drift.
"""

from __future__ import annotations

import os
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
"""Directory containing this module: ``.../rag_system_v2/src``."""

RAG_V2_ROOT: Path = _SRC_DIR.parent
"""Default install root: ``.../rag_system_v2`` (contains ``src/``, ``data/``, ``logs/``)."""

# Canonical filenames under ``<base_dir>/data/``
PARENTS_STORE_FILENAME = "parents.sqlite"
CHUNKS_JSONL_FILENAME = "chunks.jsonl"
BM25_INDEX_FILENAME = "bm25_index.pkl"
MANIFEST_FILENAME = "manifest.json"
QDRANT_DIRNAME = "qdrant"


def default_rag_v2_base_dir() -> Path:
    """Resolve RAG v2 root: env overrides, else package root next to ``src/``."""
    override = os.environ.get("RAG_V2_BASE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return RAG_V2_ROOT.resolve()


def ensure_rag_v2_base_dir_env() -> Path:
    """
    If ``RAG_V2_BASE_DIR`` is unset, set it to the default package root and return it.

    For CLI entrypoints that may be launched without the parent process (e.g. orchestrator)
    having set the variable.
    """
    if not os.environ.get("RAG_V2_BASE_DIR"):
        os.environ["RAG_V2_BASE_DIR"] = str(RAG_V2_ROOT.resolve())
    return Path(os.environ["RAG_V2_BASE_DIR"]).expanduser().resolve()
