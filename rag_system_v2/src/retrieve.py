"""
RAG System V2 - Retrieval Orchestrator Module
=============================================
Purpose: Orchestrate hybrid retrieval (BM25 + Vector + RRF + Parent expansion)
Inputs: Query string
Outputs: Retrieved chunks with parent context
Failure modes:
  - Index not loaded → raise clear error
  - Empty query → return empty results
  - All scores below threshold → signal to router
Logging: INFO for retrieval stats, DEBUG for candidates

RETRIEVAL PIPELINE:
1. Embed query → Vector search on Qdrant
2. Tokenize query → BM25 search
3. RRF merge → Combined ranking
4. (Optional) Rerank if needed
5. Parent expansion → Include parent context for top children
6. Return with full score breakdown for router
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved chunk with all metadata."""
    chunk_id: str
    text: str
    parent_id: str
    parent_text: Optional[str] = None
    
    # Scores
    rrf_score: float = 0.0
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rerank_score: Optional[float] = None
    
    # Metadata
    doc_id: str = ""
    source_path: str = ""
    file_type: str = ""
    page_num: Optional[int] = None
    section_headers: List[str] = field(default_factory=list)
    
    # Position info for citations
    char_start: int = 0
    char_end: int = 0
    
    def citation_id(self) -> str:
        """Generate citation ID for this chunk."""
        # Format: DOC_PREFIX:PAGE:CHILD_IDX or DOC_PREFIX:IDX if no page
        doc_prefix = self.doc_id[:6] if self.doc_id else "unknown"
        
        if self.page_num is not None:
            # Extract child index from chunk_id (it's a hash, so just use chunk_id prefix)
            return f"{doc_prefix}:{self.page_num}:{self.chunk_id[:4]}"
        else:
            return f"{doc_prefix}:{self.chunk_id[:6]}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "chunk_id": self.chunk_id,
            "citation_id": self.citation_id(),
            "text_preview": self.text[:200] + "..." if len(self.text) > 200 else self.text,
            "parent_id": self.parent_id,
            "has_parent_text": self.parent_text is not None,
            "rrf_score": round(self.rrf_score, 6) if self.rrf_score else None,
            "vector_score": round(self.vector_score, 6) if self.vector_score else None,
            "bm25_score": round(self.bm25_score, 4) if self.bm25_score else None,
            "rerank_score": round(self.rerank_score, 4) if self.rerank_score else None,
            "source_path": self.source_path,
            "page_num": self.page_num,
            "section_headers": self.section_headers
        }


@dataclass
class RetrievalResult:
    """Complete result from retrieval pipeline."""
    query: str
    chunks: List[RetrievedChunk]
    
    # Timing
    vector_time_ms: float = 0.0
    bm25_time_ms: float = 0.0
    merge_time_ms: float = 0.0
    parent_time_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Stats
    vector_candidates: int = 0
    bm25_candidates: int = 0
    merged_candidates: int = 0
    final_count: int = 0
    
    # Quality signals for router
    top_score: float = 0.0
    score_gap: float = 0.0  # Gap between #1 and #2
    evidence_count: int = 0  # Chunks above threshold
    query_term_coverage: float = 0.0  # Fraction of query terms found
    retriever_agreement: bool = False  # Did both retrievers agree on top?
    
    def to_trace_dict(self) -> Dict:
        """Convert to dictionary for trace logging."""
        return {
            "query": self.query,
            "timing": {
                "vector_ms": round(self.vector_time_ms, 2),
                "bm25_ms": round(self.bm25_time_ms, 2),
                "merge_ms": round(self.merge_time_ms, 2),
                "parent_ms": round(self.parent_time_ms, 2),
                "total_ms": round(self.total_time_ms, 2)
            },
            "stats": {
                "vector_candidates": self.vector_candidates,
                "bm25_candidates": self.bm25_candidates,
                "merged_candidates": self.merged_candidates,
                "final_count": self.final_count
            },
            "quality_signals": {
                "top_score": round(self.top_score, 4),
                "score_gap": round(self.score_gap, 4),
                "evidence_count": self.evidence_count,
                "query_term_coverage": round(self.query_term_coverage, 3),
                "retriever_agreement": self.retriever_agreement
            },
            "chunks": [c.to_dict() for c in self.chunks[:5]]  # Top 5 for trace
        }


class Retriever:
    """
    Main retrieval orchestrator.
    
    Combines:
    - Qdrant vector search
    - BM25 lexical search
    - RRF fusion
    - Parent expansion
    """
    
    def __init__(self, config=None):
        """
        Initialize retriever.
        
        Args:
            config: Config object (or None to load default)
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from config import get_config
        self.config = config or get_config()
        
        # Lazy-loaded components
        self._bm25_index = None
        self._qdrant_index = None
        self._embedding_model = None
        self._parent_store = None
        self._chunks_data: Dict[str, Dict] = {}  # chunk_id -> chunk data
    
    def _load_bm25(self):
        """Load BM25 index."""
        if self._bm25_index is not None:
            return self._bm25_index
        
        from index_bm25 import BM25Index
        
        path = self.config.paths.bm25_index_path
        if not path.exists():
            raise FileNotFoundError(f"BM25 index not found: {path}. Run index_bm25.py first.")
        
        self._bm25_index = BM25Index.load(path)
        logger.info(f"BM25 index loaded: {self._bm25_index._total_docs} docs")
        return self._bm25_index
    
    def _load_qdrant(self):
        """Load Qdrant index."""
        if self._qdrant_index is not None:
            return self._qdrant_index
        
        from index_qdrant import QdrantIndex, EmbeddingModel
        
        # Load embedding model
        self._embedding_model = EmbeddingModel(
            model_name=self.config.embedding.model,
            device=self.config.embedding.device,
            normalize=self.config.embedding.normalize
        )
        
        # Load Qdrant
        self._qdrant_index = QdrantIndex(
            qdrant_path=self.config.paths.qdrant_dir,
            collection_name=self.config.qdrant.collection_name,
            embedding_dim=self._embedding_model.dimension
        )
        
        # Load ID mapping
        mapping_path = self.config.paths.qdrant_dir / "id_mapping.json"
        if mapping_path.exists():
            self._qdrant_index.load_id_mapping(mapping_path)
        
        logger.info(f"Qdrant index loaded: {self._qdrant_index.count()} vectors")
        return self._qdrant_index
    
    def _load_parent_store(self):
        """Load parent chunk store."""
        if self._parent_store is not None:
            return self._parent_store
        
        from ingest import ParentStore
        
        self._parent_store = ParentStore(self.config.paths.parents_db_path)
        return self._parent_store
    
    def _load_chunks_data(self):
        """Load chunk data from JSONL for text lookup."""
        if self._chunks_data:
            return self._chunks_data
        
        chunks_path = self.config.paths.chunks_jsonl_path
        if not chunks_path.exists():
            logger.warning(f"Chunks JSONL not found: {chunks_path}")
            return self._chunks_data
        
        with open(chunks_path, 'r', encoding='utf-8') as f:
            for line in f:
                chunk = json.loads(line)
                self._chunks_data[chunk["chunk_id"]] = chunk
        
        logger.info(f"Loaded {len(self._chunks_data)} chunks from JSONL")
        return self._chunks_data
    
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        include_parents: bool = True,
        evidence_threshold: float = None
    ) -> RetrievalResult:
        """
        Execute full retrieval pipeline.
        
        Args:
            query: Search query
            top_k: Number of final results
            include_parents: Whether to expand to parent chunks
            evidence_threshold: Min score to count as evidence (for router)
            
        Returns:
            RetrievalResult with chunks and quality signals
        """
        start_time = time.time()
        
        if not query.strip():
            return RetrievalResult(query=query, chunks=[])
        
        if evidence_threshold is None:
            evidence_threshold = self.config.router.evidence_threshold
        
        # Initialize result
        result = RetrievalResult(query=query, chunks=[])
        
        # Vector search
        t0 = time.time()
        qdrant = self._load_qdrant()
        query_embedding = self._embedding_model.embed_single(query)
        vector_results = qdrant.search(
            query_embedding,
            top_k=self.config.retrieval.vector_top_k
        )
        result.vector_time_ms = (time.time() - t0) * 1000
        result.vector_candidates = len(vector_results)
        
        # BM25 search
        t0 = time.time()
        bm25 = self._load_bm25()
        bm25_results = bm25.search(query, top_k=self.config.retrieval.bm25_top_k)
        result.bm25_time_ms = (time.time() - t0) * 1000
        result.bm25_candidates = len(bm25_results)
        
        # Compute query term coverage (using BM25 tokenizer)
        query_terms = set(bm25.tokenizer.tokenize(query))
        
        # RRF merge
        t0 = time.time()
        from merge_rrf import RRFMerger
        merger = RRFMerger(k=self.config.retrieval.rrf_k)
        merged, merge_stats = merger.merge(
            vector_results,
            bm25_results,
            top_k=self.config.retrieval.fusion_top_k
        )
        result.merge_time_ms = (time.time() - t0) * 1000
        result.merged_candidates = len(merged)
        
        # Get agreement signal
        agreement = merger.get_agreement_signal(merged)
        result.retriever_agreement = agreement.get("top_1_agreement", False)
        
        # Load chunk data
        chunks_data = self._load_chunks_data()
        
        # Build retrieved chunks
        retrieved_chunks = []
        for i, m in enumerate(merged[:top_k]):
            chunk_data = chunks_data.get(m.chunk_id, {})
            
            chunk = RetrievedChunk(
                chunk_id=m.chunk_id,
                text=chunk_data.get("text_original", ""),
                parent_id=chunk_data.get("parent_id", ""),
                rrf_score=m.rrf_score,
                vector_score=m.vector_score,
                bm25_score=m.bm25_score,
                doc_id=chunk_data.get("doc_id", ""),
                source_path=chunk_data.get("source_path", ""),
                file_type=chunk_data.get("file_type", ""),
                page_num=chunk_data.get("page_num"),
                section_headers=chunk_data.get("section_headers", []),
                char_start=chunk_data.get("char_start", 0),
                char_end=chunk_data.get("char_end", 0)
            )
            retrieved_chunks.append(chunk)
            
            # Compute query term coverage for top chunk
            if i == 0 and query_terms:
                coverage = bm25.get_term_coverage(query, m.chunk_id)
                result.query_term_coverage = coverage
        
        # Parent expansion
        t0 = time.time()
        if include_parents and retrieved_chunks:
            parent_store = self._load_parent_store()
            
            # Get unique parent IDs
            seen_parents = set()
            for chunk in retrieved_chunks:
                if chunk.parent_id and chunk.parent_id not in seen_parents:
                    parent = parent_store.get_parent(chunk.parent_id)
                    if parent:
                        chunk.parent_text = parent.text_original
                    seen_parents.add(chunk.parent_id)
                    
                    if len(seen_parents) >= self.config.retrieval.max_parents:
                        break
        
        result.parent_time_ms = (time.time() - t0) * 1000
        
        # Compute quality signals
        result.chunks = retrieved_chunks
        result.final_count = len(retrieved_chunks)
        
        if retrieved_chunks:
            result.top_score = retrieved_chunks[0].rrf_score
            if len(retrieved_chunks) > 1:
                result.score_gap = retrieved_chunks[0].rrf_score - retrieved_chunks[1].rrf_score
            
            # Count evidence (chunks above threshold)
            result.evidence_count = sum(
                1 for c in retrieved_chunks
                if c.rrf_score >= evidence_threshold
            )
        
        result.total_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"Retrieved {result.final_count} chunks in {result.total_time_ms:.1f}ms "
            f"(vec:{result.vector_time_ms:.1f}ms, bm25:{result.bm25_time_ms:.1f}ms)"
        )
        
        return result
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[RetrievedChunk]:
        """Get a single chunk by ID (for citation verification)."""
        chunks_data = self._load_chunks_data()
        
        if chunk_id not in chunks_data:
            return None
        
        chunk_data = chunks_data[chunk_id]
        return RetrievedChunk(
            chunk_id=chunk_id,
            text=chunk_data.get("text_original", ""),
            parent_id=chunk_data.get("parent_id", ""),
            doc_id=chunk_data.get("doc_id", ""),
            source_path=chunk_data.get("source_path", ""),
            file_type=chunk_data.get("file_type", ""),
            page_num=chunk_data.get("page_num"),
            section_headers=chunk_data.get("section_headers", [])
        )


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import argparse
    import sys
    
    sys.path.insert(0, str(Path(__file__).parent))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description="Test retrieval")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="Number of results")
    parser.add_argument("--no-parents", action="store_true", help="Skip parent expansion")
    
    args = parser.parse_args()
    
    retriever = Retriever()
    result = retriever.retrieve(
        query=args.query,
        top_k=args.top_k,
        include_parents=not args.no_parents
    )
    
    print(f"\n{'='*60}")
    print(f"Query: {result.query}")
    print(f"Results: {result.final_count} chunks in {result.total_time_ms:.1f}ms")
    print(f"Quality signals:")
    print(f"  top_score: {result.top_score:.4f}")
    print(f"  score_gap: {result.score_gap:.4f}")
    print(f"  evidence_count: {result.evidence_count}")
    print(f"  query_term_coverage: {result.query_term_coverage:.2f}")
    print(f"  retriever_agreement: {result.retriever_agreement}")
    print(f"{'='*60}")
    
    for i, chunk in enumerate(result.chunks, 1):
        print(f"\n[{i}] {chunk.citation_id()} (rrf: {chunk.rrf_score:.4f})")
        print(f"    Source: {chunk.source_path}")
        if chunk.section_headers:
            print(f"    Section: {' > '.join(chunk.section_headers)}")
        print(f"    Text: {chunk.text[:300]}...")
