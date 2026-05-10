"""
RAG System V2 Configuration Module
==================================
Purpose: Centralized configuration with environment variable overrides
Inputs: Environment variables, defaults
Outputs: Config dataclass instances
Failure modes: Invalid env values (validated on load), missing required paths
Logging: INFO for config load, WARN for overrides, ERROR for validation failures

ARCHITECTURE NOTE:
- All thresholds are INITIAL SAFE DEFAULTS
- MUST be calibrated using eval.py against your test set
- Override via environment variables: RAG_V2_<SETTING_NAME>
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from enum import Enum

try:
    from repo_paths import (
        BM25_INDEX_FILENAME,
        CHUNKS_JSONL_FILENAME,
        MANIFEST_FILENAME,
        PARENTS_STORE_FILENAME,
        QDRANT_DIRNAME,
        default_rag_v2_base_dir,
    )
except ImportError:
    from .repo_paths import (
        BM25_INDEX_FILENAME,
        CHUNKS_JSONL_FILENAME,
        MANIFEST_FILENAME,
        PARENTS_STORE_FILENAME,
        QDRANT_DIRNAME,
        default_rag_v2_base_dir,
    )

# Configure module logger
logger = logging.getLogger(__name__)


class EmbeddingModel(Enum):
    """Supported embedding models - bge-small chosen for technical/crypto docs."""
    BGE_SMALL = "BAAI/bge-small-en-v1.5"  # 384 dims, good for technical
    NOMIC_EMBED = "nomic-ai/nomic-embed-text-v1.5"  # 768 dims, alternative
    MINILM = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dims, general


class RerankModel(Enum):
    """Supported reranking models."""
    MS_MARCO_MINILM = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RouterDecision(Enum):
    """Router output decisions - fail-closed design."""
    NO_RETRIEVAL = "NO_RETRIEVAL"  # Chitchat, system commands
    RETRIEVE_AND_ANSWER = "RETRIEVE_AND_ANSWER"  # Docs-grounded answer
    ASK_CLARIFY = "ASK_CLARIFY"  # Ambiguous or medium confidence
    REFUSE_NO_EVIDENCE = "REFUSE_NO_EVIDENCE"  # Low confidence or out-of-corpus


class ModelTier(Enum):
    """Model selection for multi-model routing."""
    FAST = "fast"  # 7B model - query rewrite, clarify, format
    SMART = "smart"  # 13B-70B model - synthesis when RETRIEVE_AND_ANSWER


@dataclass
class PathConfig:
    """File system paths configuration."""
    base_dir: Path = field(default_factory=default_rag_v2_base_dir)
    
    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"
    
    @property
    def qdrant_dir(self) -> Path:
        return self.data_dir / QDRANT_DIRNAME
    
    @property
    def bm25_index_path(self) -> Path:
        return self.data_dir / BM25_INDEX_FILENAME
    
    @property
    def parents_db_path(self) -> Path:
        return self.data_dir / PARENTS_STORE_FILENAME
    
    @property
    def chunks_jsonl_path(self) -> Path:
        return self.data_dir / CHUNKS_JSONL_FILENAME
    
    @property
    def manifest_path(self) -> Path:
        return self.data_dir / MANIFEST_FILENAME
    
    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"
    
    @property
    def query_trace_path(self) -> Path:
        return self.logs_dir / "query_trace.jsonl"
    
    @property
    def reports_dir(self) -> Path:
        return self.base_dir / "reports"
    
    @property
    def eval_report_path(self) -> Path:
        return self.reports_dir / "latest.json"


@dataclass
class ChunkingConfig:
    """Parent-child chunking configuration."""
    # Parent chunks: preserve structure, larger context
    parent_min_tokens: int = 900
    parent_max_tokens: int = 1200
    parent_target_tokens: int = 1000
    
    # Child chunks: indexed for retrieval
    child_min_tokens: int = 200
    child_max_tokens: int = 350
    child_target_tokens: int = 275
    child_overlap_tokens: int = 50
    
    # Approximation: 1 token ≈ 4 characters (conservative for English)
    chars_per_token: float = 4.0
    
    @property
    def parent_min_chars(self) -> int:
        return int(self.parent_min_tokens * self.chars_per_token)
    
    @property
    def parent_max_chars(self) -> int:
        return int(self.parent_max_tokens * self.chars_per_token)
    
    @property
    def child_min_chars(self) -> int:
        return int(self.child_min_tokens * self.chars_per_token)
    
    @property
    def child_max_chars(self) -> int:
        return int(self.child_max_tokens * self.chars_per_token)
    
    @property
    def child_overlap_chars(self) -> int:
        return int(self.child_overlap_tokens * self.chars_per_token)


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""
    model: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_EMBEDDING_MODEL",
        EmbeddingModel.BGE_SMALL.value
    ))
    device: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_EMBEDDING_DEVICE",
        "cpu"  # Safe default; auto-detect CUDA in code
    ))
    normalize: bool = True  # L2 normalize for cosine similarity
    batch_size: int = 32
    cache_embeddings: bool = True  # Disk cache by chunk_hash
    
    @property
    def dimensions(self) -> int:
        """Return embedding dimensions based on model."""
        if "bge-small" in self.model.lower():
            return 384
        elif "nomic" in self.model.lower():
            return 768
        elif "minilm" in self.model.lower():
            return 384
        else:
            logger.warning(f"Unknown model {self.model}, assuming 384 dims")
            return 384


@dataclass
class QdrantConfig:
    """Qdrant vector database configuration."""
    collection_name: str = "rag_v2_children"
    distance_metric: str = "Cosine"  # Cosine for normalized embeddings
    # Payload fields to store
    payload_fields: List[str] = field(default_factory=lambda: [
        "doc_id", "parent_id", "child_index", "chunk_hash",
        "source_path", "file_type", "page_num", "section_headers"
    ])
    # HNSW index params (Qdrant default is good for <1M vectors)
    hnsw_m: int = 16
    hnsw_ef_construct: int = 100


@dataclass
class BM25Config:
    """BM25 lexical index configuration."""
    k1: float = 1.5  # Term frequency saturation
    b: float = 0.75  # Document length normalization
    # Tokenization
    lowercase: bool = True
    remove_stopwords: bool = False  # Keep for crypto tickers like "SOL", "BTC"
    min_token_length: int = 1


@dataclass
class RetrievalConfig:
    """Hybrid retrieval configuration."""
    # Initial retrieval counts (before rerank)
    vector_top_k: int = 50
    bm25_top_k: int = 50
    
    # RRF fusion
    rrf_k: int = 60  # RRF constant (standard is 60)
    
    # After fusion, before rerank
    fusion_top_k: int = 40
    
    # After rerank
    final_top_k: int = 10
    
    # Parent expansion: how many parents to include
    max_parents: int = 5


@dataclass
class RerankConfig:
    """Reranking configuration."""
    model: str = RerankModel.MS_MARCO_MINILM.value
    device: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_RERANK_DEVICE",
        "cpu"
    ))
    batch_size: int = 16
    
    # Conditional rerank thresholds (CALIBRATE WITH EVAL)
    # Skip rerank if top vector AND top bm25 both above this
    skip_threshold: float = 0.70
    
    # Score bands (raw cross-encoder scores, NOT 0-1 normalized)
    # These MUST be calibrated from your eval set
    high_confidence_raw: float = 8.0  # Cross-encoder raw score
    medium_confidence_raw: float = 4.0
    low_confidence_raw: float = 1.0


@dataclass
class RouterConfig:
    """Router decision thresholds - MUST CALIBRATE WITH EVAL."""
    # Confidence thresholds (effective_score blends rerank + RRF top; typical good hits ~0.32–0.55)
    # Defaults aligned with RRF scale (~0.03) + cross-encoder — tune with eval.py
    t_direct_confidence: float = float(os.getenv("RAG_V2_T_DIRECT", "0.75"))
    t_retrieve_confidence: float = float(os.getenv("RAG_V2_T_RETRIEVE", "0.33"))
    t_clarify_confidence: float = float(os.getenv("RAG_V2_T_CLARIFY", "0.28"))
    t_refuse_threshold: float = float(os.getenv("RAG_V2_T_REFUSE", "0.25"))
    
    # Evidence quality signals
    min_evidence_count: int = 2  # Need at least N chunks above threshold
    # RRF scores are ~1/(k+rank) per list; with k=60 and overlap, tops are typically ~0.02–0.04 — not on a 0–1 retrieval scale
    evidence_threshold: float = float(os.getenv("RAG_V2_EVIDENCE_THRESHOLD", "0.015"))
    
    # Ambiguity detection
    score_gap_suspicious: float = 0.30  # Gap between #1 and #2
    min_query_tokens: int = 3  # Below this, likely too short
    
    # Coverage heuristic
    min_query_term_coverage: float = 0.50  # % of query terms found in top chunks
    
    # Chitchat detection patterns
    chitchat_patterns: List[str] = field(default_factory=lambda: [
        r"^(hi|hello|hey|thanks|thank you|bye|goodbye)\b",
        r"^how are you",
        r"^what('s| is) your name",
        r"^(ok|okay|sure|yes|no|yep|nope)\s*$",
    ])
    
    # Prompt injection detection patterns (in retrieved text)
    injection_patterns: List[str] = field(default_factory=lambda: [
        # Baseline jailbreak / delimiter stack (compiled case-insensitive in router)
        r"ignore (previous|above|all) instructions",
        r"ignore\s+(?:all\s+)?(?:previous|above)\s+instructions",
        r"disregard (previous|above|all)",
        r"disregard\s+safety\s+guidelines",
        r"you are now",
        r"new instructions:",
        r"system prompt:",
        r"</?(system|user|assistant)>",
        r"IMPORTANT:.*override",
        # Role / fence / banner tokens common in adversarial wraps
        r"(?m)^\s*system\s*:",
        r"```\s*\n?\s*you\s+must\s+now\s+follow",
        r"\[\[\s*override\s*\]\]",
    ])


@dataclass
class LLMConfig:
    """LM Studio LLM configuration."""
    # OpenAI client requires a string; LM Studio often accepts any placeholder when auth is off.
    api_key: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_LLM_API_KEY",
        os.getenv("OPENAI_API_KEY")
        or os.getenv("LM_STUDIO_API_KEY")
        or "lm-studio",
    ))

    base_url: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_LLM_BASE_URL",
        "http://127.0.0.1:1234/v1"
    ))
    
    # Model names as configured in LM Studio
    fast_model: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_FAST_MODEL",
        "fast"  # 7B model alias
    ))
    smart_model: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_SMART_MODEL",
        "smart"  # 13B-70B model alias
    ))
    
    # Generation params
    max_tokens: int = 2048
    temperature: float = 0.1  # Low for factual grounding
    stream: bool = True  # Streaming preferred
    
    # Timeouts
    timeout_seconds: int = 120
    
    # Context budget (chars for reference text are derived in PromptBuilder using chunking.chars_per_token)
    max_context_tokens: int = field(default_factory=lambda: int(os.getenv(
        "RAG_V2_MAX_CONTEXT_TOKENS",
        "4096",
    )))


@dataclass
class CitationConfig:
    """Citation format and verification."""
    # Format: DOCSHA:PAGE:CHILDIDX
    # Example: a1b2c3:5:2 means doc hash a1b2c3, page 5, child chunk index 2
    separator: str = ":"
    
    # Verification thresholds
    min_overlap_ratio: float = 0.20  # Answer text must overlap 20% with cited chunk
    require_citations: bool = True  # Every factual sentence needs citation
    max_regeneration_attempts: int = 1  # Retry once if citations missing


@dataclass
class ObservabilityConfig:
    """Logging and tracing configuration."""
    log_level: str = field(default_factory=lambda: os.getenv(
        "RAG_V2_LOG_LEVEL",
        "INFO"
    ))
    trace_enabled: bool = True
    trace_max_candidates: int = 20  # Max candidates to log per stage
    
    # Performance targets
    p95_latency_ms: int = 3000  # Target p95 < 3 seconds


@dataclass
class Config:
    """Master configuration container."""
    paths: PathConfig = field(default_factory=PathConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    bm25: BM25Config = field(default_factory=BM25Config)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    citation: CitationConfig = field(default_factory=CitationConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    
    def validate(self) -> List[str]:
        """Validate configuration, return list of errors."""
        errors = []
        
        # Path validation
        if not self.paths.base_dir.exists():
            errors.append(f"Base directory does not exist: {self.paths.base_dir}")
        
        # Threshold sanity checks
        if self.router.t_direct_confidence <= self.router.t_retrieve_confidence:
            errors.append("t_direct_confidence must be > t_retrieve_confidence")
        if self.router.t_retrieve_confidence <= self.router.t_clarify_confidence:
            errors.append("t_retrieve_confidence must be > t_clarify_confidence")
        if self.router.t_clarify_confidence <= self.router.t_refuse_threshold:
            errors.append("t_clarify_confidence must be > t_refuse_threshold")
        
        # Embedding dimensions must match Qdrant if collection exists
        # (This is checked at runtime when connecting)
        
        return errors
    
    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.qdrant_dir.mkdir(parents=True, exist_ok=True)
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        self.paths.reports_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load and validate configuration."""
    config = Config()
    
    # Validate
    errors = config.validate()
    if errors:
        for err in errors:
            logger.error(f"Config validation error: {err}")
        # Don't raise - allow startup with warnings for development
        # In prod, you'd raise ConfigurationError(errors)
    
    # Ensure directories exist
    config.ensure_directories()
    
    logger.info(f"Configuration loaded from base: {config.paths.base_dir}")
    logger.info(f"Embedding model: {config.embedding.model}")
    logger.info(f"LLM base URL: {config.llm.base_url}")
    
    return config


# Module-level singleton
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create config singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


if __name__ == "__main__":
    # Test configuration loading
    logging.basicConfig(level=logging.INFO)
    cfg = get_config()
    print(f"Base dir: {cfg.paths.base_dir}")
    print(f"Qdrant dir: {cfg.paths.qdrant_dir}")
    print(f"Embedding dims: {cfg.embedding.dimensions}")
    print(f"Router thresholds: direct={cfg.router.t_direct_confidence}, "
          f"retrieve={cfg.router.t_retrieve_confidence}, "
          f"clarify={cfg.router.t_clarify_confidence}, "
          f"refuse={cfg.router.t_refuse_threshold}")
    
    errors = cfg.validate()
    if errors:
        print(f"Validation errors: {errors}")
    else:
        print("Configuration valid!")
