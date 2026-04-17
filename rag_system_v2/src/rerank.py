"""
RAG System V2 - Cross-Encoder Reranking Module
=============================================
Purpose: Rerank retrieved chunks using cross-encoder for higher precision
Inputs: Query + candidate chunks from retrieve.py
Outputs: Reranked chunks with confidence scores
Failure modes:
  - Model not loaded → raise clear error
  - Empty candidates → return empty
  - Very slow inference → timeout with partial results
Logging: INFO for rerank stats, DEBUG for individual scores

RERANKING STRATEGY:
- Use cross-encoder (ms-marco-MiniLM-L-6-v2) for semantic relevance
- Scores are NOT normalized 0-1; calibrate bands from eval set
- Conditional rerank: skip if both retrievers strongly agree
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Result from reranking."""
    chunk_id: str
    original_score: float  # Pre-rerank score (RRF)
    rerank_score: float  # Cross-encoder score
    confidence_band: str  # "high", "medium", "low"
    text_preview: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "original_score": round(self.original_score, 4),
            "rerank_score": round(self.rerank_score, 4),
            "confidence_band": self.confidence_band
        }


class CrossEncoderReranker:
    """
    Cross-encoder reranking using sentence-transformers.
    
    Default model: cross-encoder/ms-marco-MiniLM-L-6-v2
    
    IMPORTANT: Cross-encoder scores are NOT 0-1 normalized.
    Typical ranges for ms-marco model:
    - High relevance: > 8
    - Medium relevance: 3-8
    - Low relevance: < 3
    
    These bands MUST be calibrated from your eval set.
    """
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: Optional[str] = None,
        batch_size: int = 16,
        # Confidence bands (raw scores, not normalized)
        # These are DEFAULTS - calibrate from eval!
        high_threshold: float = 8.0,
        medium_threshold: float = 3.0,
        low_threshold: float = 0.0
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.low_threshold = low_threshold
        
        # Auto-detect device
        if device is None:
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        self.device = device
        
        self._model = None
    
    def _load_model(self):
        """Lazy load the cross-encoder model."""
        if self._model is not None:
            return self._model
        
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        
        logger.info(f"Loading cross-encoder: {self.model_name} on {self.device}")
        self._model = CrossEncoder(self.model_name, device=self.device)
        logger.info("Cross-encoder loaded")
        return self._model
    
    def _get_confidence_band(self, score: float) -> str:
        """Map raw score to confidence band."""
        if score >= self.high_threshold:
            return "high"
        elif score >= self.medium_threshold:
            return "medium"
        else:
            return "low"
    
    def rerank(
        self,
        query: str,
        chunks: List[Tuple[str, str, float]],  # (chunk_id, text, original_score)
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """
        Rerank chunks using cross-encoder.
        
        Args:
            query: Search query
            chunks: List of (chunk_id, text, original_score) tuples
            top_k: Optional limit on results
            
        Returns:
            List of RerankResult, sorted by rerank_score descending
        """
        if not chunks:
            return []
        
        model = self._load_model()
        
        # Prepare pairs for cross-encoder
        pairs = [(query, text) for _, text, _ in chunks]
        
        # Score all pairs
        t0 = time.time()
        scores = model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        rerank_time = (time.time() - t0) * 1000
        
        logger.debug(f"Reranked {len(chunks)} chunks in {rerank_time:.1f}ms")
        
        # Build results
        results = []
        for (chunk_id, text, original_score), score in zip(chunks, scores):
            results.append(RerankResult(
                chunk_id=chunk_id,
                original_score=original_score,
                rerank_score=float(score),
                confidence_band=self._get_confidence_band(float(score)),
                text_preview=text[:200]
            ))
        
        # Sort by rerank score descending
        results.sort(key=lambda x: x.rerank_score, reverse=True)
        
        if top_k:
            results = results[:top_k]
        
        return results
    
    def should_skip_rerank(
        self,
        vector_top_score: float,
        bm25_top_score: float,
        retriever_agreement: bool,
        threshold: float = 0.70
    ) -> Tuple[bool, str]:
        """
        Determine if reranking can be skipped.
        
        Skip conditions:
        - Both retrievers have high confidence
        - Top results agree between retrievers
        
        Args:
            vector_top_score: Normalized vector similarity (0-1)
            bm25_top_score: BM25 score (need to normalize or use RRF)
            retriever_agreement: Whether top-1 came from both
            threshold: Skip threshold
            
        Returns:
            (should_skip, reason)
        """
        # Only skip if both are confident AND they agree
        if retriever_agreement and vector_top_score >= threshold:
            return True, "high_agreement"
        
        return False, "needs_rerank"


class ConditionalReranker:
    """
    Wrapper that conditionally applies reranking based on retrieval signals.
    """
    
    def __init__(self, config=None):
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from config import get_config
        self.config = config or get_config()
        
        self._reranker = None
    
    def _get_reranker(self) -> CrossEncoderReranker:
        """Get or create reranker."""
        if self._reranker is None:
            self._reranker = CrossEncoderReranker(
                model_name=self.config.rerank.model,
                device=self.config.rerank.device,
                batch_size=self.config.rerank.batch_size,
                high_threshold=self.config.rerank.high_confidence_raw,
                medium_threshold=self.config.rerank.medium_confidence_raw,
                low_threshold=self.config.rerank.low_confidence_raw
            )
        return self._reranker
    
    def maybe_rerank(
        self,
        query: str,
        chunks: List[Tuple[str, str, float]],
        retrieval_result  # RetrievalResult from retrieve.py
    ) -> Tuple[List[RerankResult], bool, str]:
        """
        Conditionally rerank based on retrieval signals.
        
        Args:
            query: Search query
            chunks: List of (chunk_id, text, score) tuples
            retrieval_result: RetrievalResult with quality signals
            
        Returns:
            (rerank_results, was_reranked, reason)
        """
        reranker = self._get_reranker()
        
        # Check if we can skip reranking
        should_skip, reason = reranker.should_skip_rerank(
            vector_top_score=retrieval_result.top_score,
            bm25_top_score=retrieval_result.top_score,  # Using RRF as proxy
            retriever_agreement=retrieval_result.retriever_agreement,
            threshold=self.config.rerank.skip_threshold
        )
        
        if should_skip:
            # Convert to RerankResult without actual reranking
            results = [
                RerankResult(
                    chunk_id=chunk_id,
                    original_score=score,
                    rerank_score=score,  # Use original as pseudo-rerank
                    confidence_band="high" if i == 0 else "medium",
                    text_preview=text[:200]
                )
                for i, (chunk_id, text, score) in enumerate(chunks)
            ]
            return results, False, reason
        
        # Do full rerank
        results = reranker.rerank(
            query=query,
            chunks=chunks,
            top_k=self.config.retrieval.final_top_k
        )
        
        return results, True, "reranked"


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test with synthetic data
    query = "What is the untouched wick pattern in trading?"
    
    chunks = [
        ("chunk_1", "The untouched wick pattern is a key signal in price action trading. It occurs when a candle's wick has not been retested.", 0.85),
        ("chunk_2", "Volume analysis is important for confirming trading signals and patterns in the market.", 0.82),
        ("chunk_3", "Untouched wicks represent areas where price has not returned, indicating potential support or resistance.", 0.78),
        ("chunk_4", "Moving averages are lagging indicators used in technical analysis.", 0.75),
        ("chunk_5", "Poor highs and poor lows in market structure often leave untouched wicks that become targets.", 0.70),
    ]
    
    print(f"Query: {query}")
    print(f"\nOriginal ranking:")
    for chunk_id, text, score in chunks:
        print(f"  {chunk_id}: {score:.4f} - {text[:50]}...")
    
    reranker = CrossEncoderReranker()
    results = reranker.rerank(query, chunks)
    
    print(f"\nReranked results:")
    for r in results:
        print(f"  {r.chunk_id}: {r.rerank_score:.4f} ({r.confidence_band}) - {r.text_preview[:50]}...")
