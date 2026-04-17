"""
RAG System V2 - BM25 Lexical Index Module
=========================================
Purpose: BM25 lexical search over normalized chunk text
Inputs: Child chunks from ingest.py
Outputs: BM25 scores and ranked chunk IDs
Failure modes:
  - Index corruption → rebuild from chunks.jsonl
  - Memory overflow on large corpus → stream build
  - Tokenization mismatch → ensure same tokenizer at query time
Logging: INFO for index operations, DEBUG for query details

CRITICAL: Chunk IDs MUST match exactly between BM25 and Qdrant indexes.
The chunk_id field is the stable identifier across both.
"""

import json
import logging
import math
import pickle
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class BM25Stats:
    """Statistics for BM25 scoring."""
    total_docs: int
    avg_doc_length: float
    doc_lengths: Dict[str, int]  # chunk_id -> token count
    doc_freqs: Dict[str, int]  # term -> num docs containing term
    

class BM25Tokenizer:
    """
    Tokenizer for BM25 indexing.
    
    NOTE: Keep stopwords for crypto/trading (SOL, BTC are important).
    Uses simple whitespace + punctuation splitting.
    """
    
    def __init__(
        self,
        lowercase: bool = True,
        min_token_length: int = 1,
        remove_stopwords: bool = False
    ):
        self.lowercase = lowercase
        self.min_token_length = min_token_length
        self.remove_stopwords = remove_stopwords
        
        # Basic stopwords (only used if remove_stopwords=True)
        self._stopwords = {
            'a', 'an', 'the', 'is', 'it', 'to', 'of', 'and', 'or', 'in',
            'on', 'at', 'by', 'for', 'with', 'as', 'be', 'was', 'were'
        }
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into terms.
        Returns list of tokens preserving order.
        """
        if not text:
            return []
        
        # Lowercase if configured
        if self.lowercase:
            text = text.lower()
        
        # Split on whitespace and punctuation (keep alphanumeric + underscore)
        tokens = re.findall(r'[\w]+', text)
        
        # Filter by length
        tokens = [t for t in tokens if len(t) >= self.min_token_length]
        
        # Remove stopwords if configured
        if self.remove_stopwords:
            tokens = [t for t in tokens if t not in self._stopwords]
        
        return tokens


class BM25Index:
    """
    BM25 (Okapi BM25) lexical index.
    
    Scoring formula:
    score(q, d) = sum over q_terms of:
        IDF(t) * (tf(t,d) * (k1 + 1)) / (tf(t,d) + k1 * (1 - b + b * |d|/avgdl))
    
    where:
        IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)
        N = total docs
        df(t) = doc frequency of term t
        tf(t,d) = term frequency in document d
        |d| = document length (tokens)
        avgdl = average document length
        k1, b = tuning parameters
    """
    
    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: Optional[BM25Tokenizer] = None
    ):
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or BM25Tokenizer()
        
        # Index structures
        self._inverted_index: Dict[str, Dict[str, int]] = defaultdict(dict)  # term -> {chunk_id: tf}
        self._doc_lengths: Dict[str, int] = {}  # chunk_id -> token count
        self._doc_freqs: Dict[str, int] = defaultdict(int)  # term -> num docs
        self._total_docs: int = 0
        self._avg_doc_length: float = 0.0
        
        # Chunk ID to original text mapping (for debug)
        self._chunk_texts: Dict[str, str] = {}
    
    def add_chunk(self, chunk_id: str, text: str) -> None:
        """
        Add a chunk to the index.
        
        Args:
            chunk_id: Unique stable chunk identifier
            text: Normalized text to index
        """
        tokens = self.tokenizer.tokenize(text)
        
        if not tokens:
            logger.debug(f"Empty tokenization for chunk {chunk_id}")
            return
        
        # Count term frequencies
        tf: Dict[str, int] = defaultdict(int)
        for token in tokens:
            tf[token] += 1
        
        # Update inverted index
        for term, count in tf.items():
            if chunk_id not in self._inverted_index[term]:
                self._doc_freqs[term] += 1
            self._inverted_index[term][chunk_id] = count
        
        # Store doc length
        self._doc_lengths[chunk_id] = len(tokens)
        self._chunk_texts[chunk_id] = text[:500]  # Store truncated for debug
        self._total_docs += 1
    
    def finalize(self) -> None:
        """
        Finalize index after all chunks added.
        Computes average document length.
        """
        if self._total_docs > 0:
            total_length = sum(self._doc_lengths.values())
            self._avg_doc_length = total_length / self._total_docs
        else:
            self._avg_doc_length = 0.0
        
        logger.info(f"BM25 index finalized: {self._total_docs} docs, "
                    f"{len(self._inverted_index)} terms, "
                    f"avg_length={self._avg_doc_length:.1f}")
    
    def _idf(self, term: str) -> float:
        """Compute IDF for a term."""
        df = self._doc_freqs.get(term, 0)
        if df == 0:
            return 0.0
        return math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)
    
    def _score_doc(self, query_terms: List[str], chunk_id: str) -> float:
        """Compute BM25 score for a single document."""
        doc_len = self._doc_lengths.get(chunk_id, 0)
        if doc_len == 0:
            return 0.0
        
        score = 0.0
        for term in query_terms:
            if term not in self._inverted_index:
                continue
            
            tf = self._inverted_index[term].get(chunk_id, 0)
            if tf == 0:
                continue
            
            idf = self._idf(term)
            
            # BM25 term score
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self._avg_doc_length, 1))
            score += idf * numerator / denominator
        
        return score
    
    def search(
        self,
        query: str,
        top_k: int = 50
    ) -> List[Tuple[str, float]]:
        """
        Search the index.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            
        Returns:
            List of (chunk_id, score) tuples, sorted by score descending
        """
        query_terms = self.tokenizer.tokenize(query)
        
        if not query_terms:
            logger.debug("Empty query tokenization")
            return []
        
        # Get candidate documents (union of all posting lists)
        candidates: Set[str] = set()
        for term in query_terms:
            if term in self._inverted_index:
                candidates.update(self._inverted_index[term].keys())
        
        if not candidates:
            return []
        
        # Score all candidates
        scores = []
        for chunk_id in candidates:
            score = self._score_doc(query_terms, chunk_id)
            if score > 0:
                scores.append((chunk_id, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
    
    def get_term_coverage(self, query: str, chunk_id: str) -> float:
        """
        Compute what fraction of query terms appear in chunk.
        Useful for router coverage heuristic.
        """
        query_terms = set(self.tokenizer.tokenize(query))
        if not query_terms:
            return 0.0
        
        found = 0
        for term in query_terms:
            if chunk_id in self._inverted_index.get(term, {}):
                found += 1
        
        return found / len(query_terms)
    
    def save(self, path: Path) -> None:
        """Save index to disk."""
        data = {
            "k1": self.k1,
            "b": self.b,
            "inverted_index": dict(self._inverted_index),
            "doc_lengths": self._doc_lengths,
            "doc_freqs": dict(self._doc_freqs),
            "total_docs": self._total_docs,
            "avg_doc_length": self._avg_doc_length,
            "chunk_texts": self._chunk_texts,
        }
        
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        
        logger.info(f"BM25 index saved to {path}")
    
    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        """Load index from disk."""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        
        index = cls(k1=data["k1"], b=data["b"])
        index._inverted_index = defaultdict(dict, data["inverted_index"])
        index._doc_lengths = data["doc_lengths"]
        index._doc_freqs = defaultdict(int, data["doc_freqs"])
        index._total_docs = data["total_docs"]
        index._avg_doc_length = data["avg_doc_length"]
        index._chunk_texts = data.get("chunk_texts", {})
        
        logger.info(f"BM25 index loaded from {path}: {index._total_docs} docs")
        return index
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        return {
            "total_docs": self._total_docs,
            "total_terms": len(self._inverted_index),
            "avg_doc_length": self._avg_doc_length,
            "k1": self.k1,
            "b": self.b
        }


def build_bm25_from_jsonl(
    chunks_path: Path,
    output_path: Path,
    k1: float = 1.5,
    b: float = 0.75
) -> BM25Index:
    """
    Build BM25 index from chunks JSONL file.
    
    Args:
        chunks_path: Path to chunks.jsonl from ingest.py
        output_path: Where to save the index
        k1, b: BM25 parameters
        
    Returns:
        Built BM25Index
    """
    index = BM25Index(k1=k1, b=b)
    
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line in f:
            chunk = json.loads(line)
            # Use normalized text for BM25
            index.add_chunk(
                chunk_id=chunk["chunk_id"],
                text=chunk["text_normalized"]
            )
    
    index.finalize()
    index.save(output_path)
    
    return index


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
    
    parser = argparse.ArgumentParser(description="Build BM25 index")
    parser.add_argument("chunks_file", type=Path, help="Input chunks JSONL")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output index path")
    parser.add_argument("--k1", type=float, default=1.5, help="BM25 k1 parameter")
    parser.add_argument("--b", type=float, default=0.75, help="BM25 b parameter")
    
    args = parser.parse_args()
    
    from config import get_config
    config = get_config()
    
    output_path = args.output or config.paths.bm25_index_path
    
    index = build_bm25_from_jsonl(args.chunks_file, output_path, args.k1, args.b)
    
    stats = index.get_stats()
    print(f"✓ BM25 index built: {stats['total_docs']} docs, {stats['total_terms']} terms")
    print(f"  Saved to: {output_path}")
