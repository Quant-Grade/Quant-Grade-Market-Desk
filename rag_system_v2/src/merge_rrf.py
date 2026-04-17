"""
RAG System V2 - Reciprocal Rank Fusion (RRF) Merge Module
=========================================================
Purpose: Merge BM25 and Vector search results with score logging
Inputs: Ranked lists from BM25 and Qdrant indexes
Outputs: Merged ranked list with fusion scores
Failure modes:
  - Empty result lists → return empty
  - Mismatched chunk IDs → use union with logging
  - Score scale mismatch → RRF handles this naturally
Logging: DEBUG for individual scores, INFO for merge stats

RRF FORMULA:
  score(d) = sum over rankings of: 1 / (k + rank(d))
  
Where k is a constant (typically 60) that dampens the effect of high ranks.
This naturally handles different score scales between BM25 and vector search.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum

logger = logging.getLogger(__name__)


class RetrievalSource(Enum):
    """Source of retrieval result."""
    VECTOR = "vector"
    BM25 = "bm25"
    BOTH = "both"


@dataclass
class MergedResult:
    """A single merged search result with score breakdown."""
    chunk_id: str
    rrf_score: float
    vector_rank: Optional[int] = None
    vector_score: Optional[float] = None
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    source: RetrievalSource = RetrievalSource.VECTOR
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "chunk_id": self.chunk_id,
            "rrf_score": round(self.rrf_score, 6),
            "vector_rank": self.vector_rank,
            "vector_score": round(self.vector_score, 6) if self.vector_score else None,
            "bm25_rank": self.bm25_rank,
            "bm25_score": round(self.bm25_score, 4) if self.bm25_score else None,
            "source": self.source.value
        }


@dataclass
class MergeStats:
    """Statistics from a merge operation."""
    total_candidates: int
    vector_only: int
    bm25_only: int
    overlap: int
    top_k_returned: int
    
    def to_dict(self) -> Dict:
        return {
            "total_candidates": self.total_candidates,
            "vector_only": self.vector_only,
            "bm25_only": self.bm25_only,
            "overlap": self.overlap,
            "overlap_ratio": round(self.overlap / max(self.total_candidates, 1), 3),
            "top_k_returned": self.top_k_returned
        }


class RRFMerger:
    """
    Reciprocal Rank Fusion merger for hybrid retrieval.
    
    Combines BM25 and vector search results using:
      score(d) = sum_rankings( 1 / (k + rank) )
    
    Benefits:
    - Handles different score scales naturally
    - No need for score normalization
    - Stable under rank perturbations
    """
    
    def __init__(
        self,
        k: int = 60,
        vector_weight: float = 1.0,
        bm25_weight: float = 1.0
    ):
        """
        Initialize RRF merger.
        
        Args:
            k: RRF constant (60 is standard)
            vector_weight: Weight for vector RRF contribution
            bm25_weight: Weight for BM25 RRF contribution
        """
        self.k = k
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
    
    def _rrf_score(self, rank: int, weight: float = 1.0) -> float:
        """Compute single RRF contribution."""
        return weight / (self.k + rank)
    
    def merge(
        self,
        vector_results: List[Tuple[str, float]],
        bm25_results: List[Tuple[str, float]],
        top_k: int = 50
    ) -> Tuple[List[MergedResult], MergeStats]:
        """
        Merge two ranked lists using RRF.
        
        Args:
            vector_results: List of (chunk_id, score) from vector search
            bm25_results: List of (chunk_id, score) from BM25 search
            top_k: Number of results to return
            
        Returns:
            (merged_results, merge_stats)
        """
        # Build score maps with ranks
        vector_map: Dict[str, Tuple[int, float]] = {}
        for rank, (chunk_id, score) in enumerate(vector_results, 1):
            vector_map[chunk_id] = (rank, score)
        
        bm25_map: Dict[str, Tuple[int, float]] = {}
        for rank, (chunk_id, score) in enumerate(bm25_results, 1):
            bm25_map[chunk_id] = (rank, score)
        
        # Get all unique chunk IDs
        all_chunks: Set[str] = set(vector_map.keys()) | set(bm25_map.keys())
        
        # Track overlap stats
        vector_only = len(set(vector_map.keys()) - set(bm25_map.keys()))
        bm25_only = len(set(bm25_map.keys()) - set(vector_map.keys()))
        overlap = len(set(vector_map.keys()) & set(bm25_map.keys()))
        
        # Compute RRF scores
        merged = []
        for chunk_id in all_chunks:
            rrf_score = 0.0
            vector_rank = None
            vector_score = None
            bm25_rank = None
            bm25_score = None
            
            if chunk_id in vector_map:
                vector_rank, vector_score = vector_map[chunk_id]
                rrf_score += self._rrf_score(vector_rank, self.vector_weight)
            
            if chunk_id in bm25_map:
                bm25_rank, bm25_score = bm25_map[chunk_id]
                rrf_score += self._rrf_score(bm25_rank, self.bm25_weight)
            
            # Determine source
            if vector_rank and bm25_rank:
                source = RetrievalSource.BOTH
            elif vector_rank:
                source = RetrievalSource.VECTOR
            else:
                source = RetrievalSource.BM25
            
            merged.append(MergedResult(
                chunk_id=chunk_id,
                rrf_score=rrf_score,
                vector_rank=vector_rank,
                vector_score=vector_score,
                bm25_rank=bm25_rank,
                bm25_score=bm25_score,
                source=source
            ))
        
        # Sort by RRF score descending
        merged.sort(key=lambda x: x.rrf_score, reverse=True)
        
        # Truncate to top_k
        merged = merged[:top_k]
        
        stats = MergeStats(
            total_candidates=len(all_chunks),
            vector_only=vector_only,
            bm25_only=bm25_only,
            overlap=overlap,
            top_k_returned=len(merged)
        )
        
        logger.debug(f"RRF merge: {stats.to_dict()}")
        
        return merged, stats
    
    def get_agreement_signal(
        self,
        merged_results: List[MergedResult],
        top_n: int = 3
    ) -> Dict[str, float]:
        """
        Compute agreement signals between retrievers.
        
        Useful for router decision making:
        - High agreement → more confident
        - Low agreement → may need clarification
        
        Returns:
            Dict with agreement metrics
        """
        if not merged_results:
            return {
                "top_n_both_ratio": 0.0,
                "rank_correlation": 0.0,
                "top_1_agreement": False
            }
        
        top_n_results = merged_results[:top_n]
        
        # How many of top N came from both retrievers?
        both_count = sum(1 for r in top_n_results if r.source == RetrievalSource.BOTH)
        top_n_both_ratio = both_count / len(top_n_results)
        
        # Did top-1 come from both?
        top_1_agreement = merged_results[0].source == RetrievalSource.BOTH
        
        # Simple rank correlation for overlapping results
        both_results = [r for r in merged_results if r.source == RetrievalSource.BOTH]
        if len(both_results) >= 2:
            # Spearman-ish: compare rank orderings
            vector_ranks = [r.vector_rank for r in both_results]
            bm25_ranks = [r.bm25_rank for r in both_results]
            
            # Compute rank difference sum
            rank_diffs = sum(abs(v - b) for v, b in zip(vector_ranks, bm25_ranks))
            max_diff = len(both_results) * len(merged_results)  # Theoretical max
            rank_correlation = 1.0 - (rank_diffs / max(max_diff, 1))
        else:
            rank_correlation = 0.0
        
        return {
            "top_n_both_ratio": round(top_n_both_ratio, 3),
            "rank_correlation": round(rank_correlation, 3),
            "top_1_agreement": top_1_agreement
        }


class WeightedMerger:
    """
    Alternative: Weighted score merge (requires score normalization).
    
    Use when you have calibrated score ranges and want fine control.
    Generally RRF is preferred for robustness.
    """
    
    def __init__(
        self,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
        normalize_scores: bool = True
    ):
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.normalize_scores = normalize_scores
    
    def _normalize(
        self,
        results: List[Tuple[str, float]]
    ) -> List[Tuple[str, float]]:
        """Min-max normalize scores to [0, 1]."""
        if not results:
            return []
        
        scores = [s for _, s in results]
        min_s, max_s = min(scores), max(scores)
        
        if max_s == min_s:
            return [(chunk_id, 1.0) for chunk_id, _ in results]
        
        return [
            (chunk_id, (score - min_s) / (max_s - min_s))
            for chunk_id, score in results
        ]
    
    def merge(
        self,
        vector_results: List[Tuple[str, float]],
        bm25_results: List[Tuple[str, float]],
        top_k: int = 50
    ) -> List[Tuple[str, float]]:
        """
        Merge using weighted score combination.
        
        Returns:
            List of (chunk_id, combined_score)
        """
        if self.normalize_scores:
            vector_results = self._normalize(vector_results)
            bm25_results = self._normalize(bm25_results)
        
        # Build score maps
        vector_map = {chunk_id: score for chunk_id, score in vector_results}
        bm25_map = {chunk_id: score for chunk_id, score in bm25_results}
        
        all_chunks = set(vector_map.keys()) | set(bm25_map.keys())
        
        merged = []
        for chunk_id in all_chunks:
            v_score = vector_map.get(chunk_id, 0.0)
            b_score = bm25_map.get(chunk_id, 0.0)
            combined = self.vector_weight * v_score + self.bm25_weight * b_score
            merged.append((chunk_id, combined))
        
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:top_k]


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def merge_results(
    vector_results: List[Tuple[str, float]],
    bm25_results: List[Tuple[str, float]],
    top_k: int = 50,
    k: int = 60,
    method: str = "rrf"
) -> Tuple[List[MergedResult], MergeStats]:
    """
    Convenience function to merge retrieval results.
    
    Args:
        vector_results: Vector search results
        bm25_results: BM25 search results
        top_k: Number of results to return
        k: RRF constant (if using RRF)
        method: "rrf" or "weighted"
        
    Returns:
        (merged_results, stats)
    """
    if method == "rrf":
        merger = RRFMerger(k=k)
        return merger.merge(vector_results, bm25_results, top_k)
    else:
        raise ValueError(f"Unknown merge method: {method}")


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Test with synthetic data
    vector_results = [
        ("chunk_1", 0.95),
        ("chunk_2", 0.88),
        ("chunk_3", 0.82),
        ("chunk_4", 0.75),
        ("chunk_5", 0.70),
    ]
    
    bm25_results = [
        ("chunk_2", 15.5),  # Same as vector #2
        ("chunk_6", 14.2),  # BM25 only
        ("chunk_1", 12.8),  # Same as vector #1 but lower rank
        ("chunk_7", 11.5),  # BM25 only
        ("chunk_3", 10.0),  # Same as vector #3
    ]
    
    merger = RRFMerger(k=60)
    merged, stats = merger.merge(vector_results, bm25_results, top_k=10)
    
    print(f"\nMerge Stats: {stats.to_dict()}")
    print(f"\nAgreement: {merger.get_agreement_signal(merged)}")
    print(f"\nTop Results:")
    for i, result in enumerate(merged[:5], 1):
        print(f"  {i}. {result.to_dict()}")
