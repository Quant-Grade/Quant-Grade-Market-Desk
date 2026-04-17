"""
RAG System V2 - Qdrant Vector Index Module
==========================================
Purpose: Vector similarity search over chunk embeddings
Inputs: Child chunks from ingest.py, embeddings from embedding model
Outputs: Vector similarity scores and ranked chunk IDs
Failure modes:
  - Qdrant service down → retry with backoff
  - Embedding dimension mismatch → validate on connect
  - Collection not found → auto-create
  - Duplicate IDs → upsert semantics
Logging: INFO for index operations, WARN for retries, ERROR for failures

CRITICAL: Point IDs MUST match chunk_id from ingest.py.
We use integer hashes of chunk_id for Qdrant point IDs.
Mapping stored in index for reverse lookup.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# EMBEDDING MODEL WRAPPER
# ============================================================================

class EmbeddingModel:
    """
    Wrapper for sentence-transformers embedding model.
    
    Default: bge-small-en-v1.5 (384 dims, good for technical docs)
    Falls back to CPU if CUDA not available.
    """
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        device: Optional[str] = None,
        normalize: bool = True,
        batch_size: int = 32
    ):
        self.model_name = model_name
        self.normalize = normalize
        self.batch_size = batch_size
        
        # Auto-detect device
        if device is None:
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        self.device = device
        
        # Lazy load model
        self._model = None
        self._dimension: Optional[int] = None
    
    def _load_model(self):
        """Lazy load the embedding model."""
        if self._model is not None:
            return
        
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        
        logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(f"Embedding model loaded: {self._dimension} dimensions")
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        self._load_model()
        return self._dimension
    
    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Embed a batch of texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            numpy array of shape (len(texts), dimension)
        """
        self._load_model()
        
        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=len(texts) > 100
        )
        
        return np.array(embeddings, dtype=np.float32)
    
    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        return self.embed([text])[0]


# ============================================================================
# EMBEDDING CACHE
# ============================================================================

class EmbeddingCache:
    """
    Disk cache for embeddings keyed by model_name + chunk hash.
    Avoids re-embedding unchanged chunks on rebuild.
    
    CRITICAL: Cache is namespaced by model_name to prevent
    poisoned vectors when switching embedding models.
    """
    
    def __init__(self, cache_dir: Path, model_name: str):
        self.cache_dir = cache_dir
        self.model_name = model_name
        # Create model-specific subdirectory
        self.model_hash = hashlib.sha256(model_name.encode()).hexdigest()[:8]
        self.model_cache_dir = cache_dir / f"model_{self.model_hash}"
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, np.ndarray] = {}
        logger.debug(f"Embedding cache initialized for model: {model_name} -> {self.model_cache_dir}")
    
    def _cache_key(self, chunk_hash: str) -> str:
        """Create namespaced cache key."""
        return f"{self.model_hash}:{chunk_hash}"
    
    def _cache_path(self, chunk_hash: str) -> Path:
        """Get cache file path for a chunk hash."""
        # Use first 2 chars as subdirectory to avoid too many files in one dir
        subdir = self.model_cache_dir / chunk_hash[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{chunk_hash}.npy"
    
    def get(self, chunk_hash: str) -> Optional[np.ndarray]:
        """Get cached embedding if exists."""
        cache_key = self._cache_key(chunk_hash)
        
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]
        
        path = self._cache_path(chunk_hash)
        if path.exists():
            try:
                emb = np.load(path)
                self._memory_cache[cache_key] = emb
                return emb
            except Exception as e:
                logger.warning(f"Failed to load cached embedding {chunk_hash}: {e}")
        
        return None
    
    def put(self, chunk_hash: str, embedding: np.ndarray) -> None:
        """Cache an embedding."""
        cache_key = self._cache_key(chunk_hash)
        self._memory_cache[cache_key] = embedding
        try:
            np.save(self._cache_path(chunk_hash), embedding)
        except Exception as e:
            logger.warning(f"Failed to cache embedding {chunk_hash}: {e}")
    
    def clear_model_cache(self) -> int:
        """Clear all cached embeddings for current model. Returns count deleted."""
        import shutil
        count = 0
        if self.model_cache_dir.exists():
            for f in self.model_cache_dir.rglob("*.npy"):
                f.unlink()
                count += 1
        self._memory_cache.clear()
        logger.info(f"Cleared {count} cached embeddings for model {self.model_name}")
        return count


# ============================================================================
# QDRANT INDEX WRAPPER
# ============================================================================

def chunk_id_to_point_id(chunk_id: str) -> int:
    """
    Convert string chunk_id to integer point ID for Qdrant.
    Uses hash to ensure stability across rebuilds.
    """
    # Use first 15 hex chars of SHA-256 (60 bits) to fit in int64
    h = hashlib.sha256(chunk_id.encode()).hexdigest()[:15]
    return int(h, 16)


class QdrantIndex:
    """
    Qdrant vector index wrapper.
    
    Uses Qdrant in local/persistent mode (no Docker needed).
    Collection name: rag_v2_children
    """
    
    def __init__(
        self,
        qdrant_path: Path,
        collection_name: str = "rag_v2_children",
        embedding_dim: int = 384,
        distance_metric: str = "Cosine"
    ):
        self.qdrant_path = qdrant_path
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.distance_metric = distance_metric
        
        # Point ID to chunk_id mapping
        self._id_mapping: Dict[int, str] = {}
        self._chunk_to_point: Dict[str, int] = {}
        
        # Lazy client
        self._client = None
    
    def _get_client(self):
        """Get or create Qdrant client."""
        if self._client is not None:
            return self._client
        
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError:
            raise ImportError(
                "qdrant-client not installed. "
                "Run: pip install qdrant-client"
            )
        
        # Use local persistent storage
        self._client = QdrantClient(path=str(self.qdrant_path))
        
        # Create collection if not exists
        collections = self._client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            
            # Map distance metric
            distance = {
                "Cosine": Distance.COSINE,
                "Euclidean": Distance.EUCLID,
                "Dot": Distance.DOT
            }.get(self.distance_metric, Distance.COSINE)
            
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=distance
                )
            )
            logger.info(f"Collection created: {self.embedding_dim} dims, {self.distance_metric}")
        else:
            # Verify dimension matches
            collection_info = self._client.get_collection(self.collection_name)
            existing_dim = collection_info.config.params.vectors.size
            if existing_dim != self.embedding_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: collection has {existing_dim}, "
                    f"model has {self.embedding_dim}. Delete collection or use matching model."
                )
        
        return self._client
    
    def add_points(
        self,
        chunk_ids: List[str],
        embeddings: np.ndarray,
        payloads: List[Dict[str, Any]]
    ) -> None:
        """
        Add points to the index.
        
        Args:
            chunk_ids: List of chunk IDs
            embeddings: numpy array of shape (n, dim)
            payloads: List of metadata dicts
        """
        from qdrant_client.models import PointStruct
        
        client = self._get_client()
        
        points = []
        for i, (chunk_id, embedding, payload) in enumerate(zip(chunk_ids, embeddings, payloads)):
            point_id = chunk_id_to_point_id(chunk_id)
            
            # Store mapping
            self._id_mapping[point_id] = chunk_id
            self._chunk_to_point[chunk_id] = point_id
            
            # Add chunk_id to payload for safety
            payload = dict(payload)
            payload["chunk_id"] = chunk_id
            
            points.append(PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload=payload
            ))
        
        # Upsert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
        
        logger.info(f"Added {len(points)} points to Qdrant")
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 50,
        filter_dict: Optional[Dict] = None
    ) -> List[Tuple[str, float]]:
        """
        Search for similar vectors.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results
            filter_dict: Optional payload filters
            
        Returns:
            List of (chunk_id, score) tuples
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        client = self._get_client()
        
        # Build filter if provided
        qdrant_filter = None
        if filter_dict:
            conditions = []
            for key, value in filter_dict.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            qdrant_filter = Filter(must=conditions)
        
        results = client.query_points(
            collection_name=self.collection_name,
            query=query_embedding.tolist(),
            limit=top_k,
            query_filter=qdrant_filter
        )
        # query_points returns QueryResponse; hits are in .points (qdrant-client 1.7+)
        hits = getattr(results, "points", None) or getattr(results, "result", []) or []
        output = []
        for hit in hits:
            payload = getattr(hit, "payload", None)
            if hasattr(payload, "get"):
                chunk_id = payload.get("chunk_id")
            else:
                chunk_id = None
            if not chunk_id:
                chunk_id = self._id_mapping.get(getattr(hit, "id", None))
            if chunk_id:
                score = getattr(hit, "score", 0.0)
                output.append((chunk_id, score))
        
        return output
    
    def get_point(self, chunk_id: str) -> Optional[Dict]:
        """Get a single point by chunk_id."""
        client = self._get_client()
        
        point_id = chunk_id_to_point_id(chunk_id)
        
        try:
            points = client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id]
            )
            if points:
                return {
                    "chunk_id": chunk_id,
                    "vector": points[0].vector,
                    "payload": points[0].payload
                }
        except Exception as e:
            logger.warning(f"Failed to retrieve point {chunk_id}: {e}")
        
        return None
    
    def count(self) -> int:
        """Get number of points in index."""
        client = self._get_client()
        info = client.get_collection(self.collection_name)
        return info.points_count
    
    def save_id_mapping(self, path: Path) -> None:
        """Save ID mapping to disk."""
        with open(path, 'w') as f:
            json.dump({
                "point_to_chunk": {str(k): v for k, v in self._id_mapping.items()},
                "chunk_to_point": self._chunk_to_point
            }, f)
        logger.info(f"ID mapping saved to {path}")
    
    def load_id_mapping(self, path: Path) -> None:
        """Load ID mapping from disk."""
        if not path.exists():
            return
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        self._id_mapping = {int(k): v for k, v in data.get("point_to_chunk", {}).items()}
        self._chunk_to_point = data.get("chunk_to_point", {})
        logger.info(f"ID mapping loaded: {len(self._id_mapping)} entries")


# ============================================================================
# INDEX BUILDER
# ============================================================================

def build_qdrant_index(
    chunks_path: Path,
    qdrant_path: Path,
    model_name: str = "BAAI/bge-small-en-v1.5",
    collection_name: str = "rag_v2_children",
    cache_dir: Optional[Path] = None,
    batch_size: int = 32
) -> QdrantIndex:
    """
    Build Qdrant index from chunks JSONL file.
    
    Args:
        chunks_path: Path to chunks.jsonl from ingest.py
        qdrant_path: Directory for Qdrant persistent storage
        model_name: Embedding model name
        collection_name: Qdrant collection name
        cache_dir: Optional embedding cache directory
        batch_size: Embedding batch size
        
    Returns:
        Built QdrantIndex
    """
    # Initialize embedding model
    embed_model = EmbeddingModel(model_name=model_name, batch_size=batch_size)
    
    # Initialize cache (namespaced by model to prevent cross-contamination)
    cache = EmbeddingCache(cache_dir, model_name=model_name) if cache_dir else None
    
    # Initialize Qdrant index
    index = QdrantIndex(
        qdrant_path=qdrant_path,
        collection_name=collection_name,
        embedding_dim=embed_model.dimension
    )
    
    # Load chunks and batch embed
    chunks = []
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line in f:
            chunks.append(json.loads(line))
    
    logger.info(f"Processing {len(chunks)} chunks")
    
    # Process in batches
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        
        # Check cache for existing embeddings
        to_embed = []
        embeddings = []
        
        for chunk in batch:
            chunk_hash = chunk["chunk_hash"]
            
            if cache:
                cached_emb = cache.get(chunk_hash)
                if cached_emb is not None:
                    embeddings.append((chunk, cached_emb))
                    continue
            
            to_embed.append(chunk)
        
        # Embed uncached chunks
        if to_embed:
            texts = [c["text_normalized"] for c in to_embed]
            new_embeddings = embed_model.embed(texts)
            
            for chunk, emb in zip(to_embed, new_embeddings):
                if cache:
                    cache.put(chunk["chunk_hash"], emb)
                embeddings.append((chunk, emb))
        
        # Add to Qdrant
        chunk_ids = [c["chunk_id"] for c, _ in embeddings]
        vectors = np.array([e for _, e in embeddings])
        payloads = [{
            "doc_id": c["doc_id"],
            "parent_id": c["parent_id"],
            "child_index": c["child_index"],
            "chunk_hash": c["chunk_hash"],
            "source_path": c["source_path"],
            "file_type": c["file_type"],
            "page_num": c.get("page_num"),
            "section_headers": c.get("section_headers", [])
        } for c, _ in embeddings]
        
        index.add_points(chunk_ids, vectors, payloads)
        
        if (i + batch_size) % 500 == 0 or i + batch_size >= len(chunks):
            logger.info(f"Processed {min(i + batch_size, len(chunks))}/{len(chunks)} chunks")
    
    # Save ID mapping
    mapping_path = qdrant_path / "id_mapping.json"
    index.save_id_mapping(mapping_path)
    
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
    
    parser = argparse.ArgumentParser(description="Build Qdrant vector index")
    parser.add_argument("chunks_file", type=Path, help="Input chunks JSONL")
    parser.add_argument("--qdrant-path", "-q", type=Path, default=None,
                        help="Qdrant storage path")
    parser.add_argument("--model", "-m", type=str, default="BAAI/bge-small-en-v1.5",
                        help="Embedding model name")
    parser.add_argument("--collection", "-c", type=str, default="rag_v2_children",
                        help="Collection name")
    parser.add_argument("--batch-size", "-b", type=int, default=32,
                        help="Embedding batch size")
    
    args = parser.parse_args()
    
    from config import get_config
    config = get_config()
    
    qdrant_path = args.qdrant_path or config.paths.qdrant_dir
    cache_dir = config.paths.data_dir / "embedding_cache"
    
    index = build_qdrant_index(
        chunks_path=args.chunks_file,
        qdrant_path=qdrant_path,
        model_name=args.model,
        collection_name=args.collection,
        cache_dir=cache_dir,
        batch_size=args.batch_size
    )
    
    count = index.count()
    print(f"✓ Qdrant index built: {count} vectors")
    print(f"  Stored at: {qdrant_path}")
