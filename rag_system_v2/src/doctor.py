"""
doctor.py - System Health Check & Diagnostics
==============================================
Purpose: Comprehensive health check for all RAG system components.
         Detects issues before they cause runtime failures.

Usage:
  # Full health check
  python -m src.doctor

  # Quick check (skip latency tests)
  python -m src.doctor --quick

  # Verbose output
  python -m src.doctor --verbose

Checks Performed:
  1. File existence and integrity
  2. Manifest verification
  3. Index counts and consistency
  4. Duplicate ID detection
  5. Embedding dimension match
  6. Sample query latency
  7. LM Studio connectivity

Output:
  - Console summary with ✓/✗ status
  - Detailed JSON report (optional)
"""

import sys
import time
import json
import sqlite3
import pickle
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field, asdict
from collections import Counter

from .config import get_config
from .build_all import Manifest, compute_file_hash

logger = logging.getLogger(__name__)


# ==============================================================================
# CHECK RESULTS
# ==============================================================================

@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: str  # "pass", "warn", "fail"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass 
class HealthReport:
    """Complete health report."""
    timestamp: str
    overall_status: str  # "healthy", "degraded", "unhealthy"
    checks: List[CheckResult] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    
    def add_check(self, check: CheckResult):
        self.checks.append(check)
        
    def finalize(self):
        """Compute summary and overall status."""
        self.summary = Counter(c.status for c in self.checks)
        
        if self.summary.get("fail", 0) > 0:
            self.overall_status = "unhealthy"
        elif self.summary.get("warn", 0) > 0:
            self.overall_status = "degraded"
        else:
            self.overall_status = "healthy"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "summary": dict(self.summary),
            "checks": [asdict(c) for c in self.checks]
        }


# ==============================================================================
# HEALTH CHECKER
# ==============================================================================

class HealthChecker:
    """
    Comprehensive health checker for RAG system.
    """
    
    def __init__(self, verbose: bool = False):
        self.config = get_config()
        self.verbose = verbose
        self.report = HealthReport(
            timestamp=datetime.now().isoformat(),
            overall_status="unknown"
        )
        
    def _log(self, msg: str):
        if self.verbose:
            print(f"  {msg}")
    
    # --------------------------------------------------------------------------
    # Individual Checks
    # --------------------------------------------------------------------------
    
    def check_files_exist(self) -> CheckResult:
        """Check all required files exist."""
        files = {
            self.config.paths.chunks_jsonl_path.name: self.config.paths.chunks_jsonl_path,
            self.config.paths.bm25_index_path.name: self.config.paths.bm25_index_path,
            self.config.paths.parents_db_path.name: self.config.paths.parents_db_path,
            self.config.paths.manifest_path.name: self.config.paths.manifest_path,
            self.config.paths.qdrant_dir.name: self.config.paths.qdrant_dir,
        }
        
        missing = []
        found = []
        
        for name, path in files.items():
            if path.exists():
                found.append(name)
                self._log(f"[OK] {name}")
            else:
                missing.append(name)
                self._log(f"[MISSING] {name}")
        
        if missing:
            return CheckResult(
                name="files_exist",
                status="fail",
                message=f"Missing files: {', '.join(missing)}",
                details={"missing": missing, "found": found}
            )
        
        return CheckResult(
            name="files_exist",
            status="pass",
            message=f"All {len(found)} required files present",
            details={"found": found}
        )
    
    def check_manifest(self) -> CheckResult:
        """Verify manifest integrity."""
        manifest = Manifest(self.config.paths.data_dir)
        loaded = manifest.load()
        
        if loaded is None:
            return CheckResult(
                name="manifest",
                status="fail",
                message="No manifest found - run build_all.py"
            )
        
        is_valid, issues = manifest.verify()
        
        if not is_valid:
            return CheckResult(
                name="manifest",
                status="fail",
                message=f"Manifest verification failed: {issues[0]}",
                details={"issues": issues, "manifest": loaded}
            )
        
        self._log(f"Schema: v{loaded.get('schema_version')}")
        self._log(f"Chunks: {loaded.get('chunk_count')}")
        self._log(f"Model: {loaded.get('embedding_model')}")
        
        return CheckResult(
            name="manifest",
            status="pass",
            message=f"Manifest valid (v{loaded.get('schema_version')}, {loaded.get('chunk_count')} chunks)",
            details={"manifest": loaded}
        )
    
    def check_chunks_jsonl(self) -> CheckResult:
        """Validate chunks.jsonl format and content."""
        chunks_path = self.config.paths.chunks_jsonl_path
        
        if not chunks_path.exists():
            return CheckResult(
                name="chunks_jsonl",
                status="fail",
                message=f"{chunks_path.name} not found"
            )
        
        count = 0
        chunk_ids = []
        issues = []
        
        try:
            with open(chunks_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if not line.strip():
                        continue
                    
                    try:
                        chunk = json.loads(line)
                        count += 1
                        
                        # Check required fields
                        if 'chunk_id' not in chunk:
                            issues.append(f"Line {i+1}: missing chunk_id")
                        else:
                            chunk_ids.append(chunk['chunk_id'])
                        
                        if 'text' not in chunk:
                            issues.append(f"Line {i+1}: missing text")
                        
                        # Check schema version
                        if 'schema_version' in chunk and chunk['schema_version'] != 2:
                            issues.append(f"Line {i+1}: wrong schema version")
                            
                    except json.JSONDecodeError as e:
                        issues.append(f"Line {i+1}: invalid JSON - {e}")
                        
        except Exception as e:
            return CheckResult(
                name="chunks_jsonl",
                status="fail",
                message=f"Failed to read chunks.jsonl: {e}"
            )
        
        # Check for duplicate IDs
        id_counts = Counter(chunk_ids)
        duplicates = [cid for cid, cnt in id_counts.items() if cnt > 1]
        
        if duplicates:
            issues.append(f"Duplicate chunk_ids: {len(duplicates)}")
            self._log(f"[dup] {len(duplicates)} duplicate IDs found")
        
        self._log(f"Total chunks: {count}")
        self._log(f"Unique IDs: {len(set(chunk_ids))}")
        
        if issues:
            return CheckResult(
                name="chunks_jsonl",
                status="warn" if len(issues) < 5 else "fail",
                message=f"{len(issues)} issues found in chunks.jsonl",
                details={"count": count, "issues": issues[:10], "duplicates": duplicates[:5]}
            )
        
        return CheckResult(
            name="chunks_jsonl",
            status="pass",
            message=f"{count} chunks, all valid",
            details={"count": count, "unique_ids": len(set(chunk_ids))}
        )
    
    def check_alpha_concepts_chunks_jsonl(self) -> CheckResult:
        """Validate alpha_concepts_chunks.jsonl format and content."""
        chunks_path = self.config.paths.data_dir / "alpha_concepts_chunks.jsonl"
        
        if not chunks_path.exists():
            return CheckResult(
                name="alpha_concepts_chunks_jsonl",
                status="fail",
                message="alpha_concepts_chunks.jsonl not found"
            )
        
        count = 0
        chunk_ids = []
        issues = []
        
        try:
            with open(chunks_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if not line.strip():
                        continue
                    
                    try:
                        chunk = json.loads(line)
                        count += 1
                        
                        # Check required fields (reuse core ChildChunk schema)
                        if 'chunk_id' not in chunk:
                            issues.append(f"Line {i+1}: missing chunk_id")
                        else:
                            chunk_ids.append(chunk['chunk_id'])
                        
                        if 'text_original' not in chunk and 'text' not in chunk:
                            issues.append(f"Line {i+1}: missing text_original/text")
                        
                        # Schema version alignment
                        if 'schema_version' in chunk and chunk['schema_version'] != 2:
                            issues.append(f"Line {i+1}: wrong schema version")
                            
                    except json.JSONDecodeError as e:
                        issues.append(f"Line {i+1}: invalid JSON - {e}")
                        
        except Exception as e:
            return CheckResult(
                name="alpha_concepts_chunks_jsonl",
                status="fail",
                message=f"Failed to read alpha_concepts_chunks.jsonl: {e}"
            )
        
        # Check for duplicate IDs
        id_counts = Counter(chunk_ids)
        duplicates = [cid for cid, cnt in id_counts.items() if cnt > 1]
        
        if duplicates:
            issues.append(f"Duplicate chunk_ids: {len(duplicates)}")
            self._log(f"[dup] {len(duplicates)} duplicate Alpha chunk IDs found")
        
        self._log(f"Total Alpha chunks: {count}")
        self._log(f"Unique Alpha IDs: {len(set(chunk_ids))}")
        
        if issues:
            return CheckResult(
                name="alpha_concepts_chunks_jsonl",
                status="warn" if len(issues) < 5 else "fail",
                message=f"{len(issues)} issues found in alpha_concepts_chunks.jsonl",
                details={"count": count, "issues": issues[:10], "duplicates": duplicates[:5]}
            )
        
        return CheckResult(
            name="alpha_concepts_chunks_jsonl",
            status="pass",
            message=f"{count} alpha_concepts chunks, all valid",
            details={"count": count, "unique_ids": len(set(chunk_ids))}
        )
    
    def check_bm25_index(self) -> CheckResult:
        """Validate BM25 index."""
        bm25_path = self.config.paths.bm25_index_path
        
        if not bm25_path.exists():
            return CheckResult(
                name="bm25_index",
                status="fail",
                message=f"{bm25_path.name} not found"
            )
        
        try:
            with open(bm25_path, 'rb') as f:
                bm25 = pickle.load(f)
            
            doc_count = len(bm25.doc_lengths)
            vocab_size = len(bm25.idf)
            
            self._log(f"Documents: {doc_count}")
            self._log(f"Vocabulary: {vocab_size}")
            
            # Check for empty index
            if doc_count == 0:
                return CheckResult(
                    name="bm25_index",
                    status="fail",
                    message="BM25 index is empty"
                )
            
            return CheckResult(
                name="bm25_index",
                status="pass",
                message=f"{doc_count} docs, {vocab_size} terms",
                details={"doc_count": doc_count, "vocab_size": vocab_size}
            )
            
        except Exception as e:
            return CheckResult(
                name="bm25_index",
                status="fail",
                message=f"Failed to load BM25 index: {e}"
            )
    
    def check_parents_db(self) -> CheckResult:
        """Validate parents SQLite database."""
        parents_path = self.config.paths.parents_db_path
        
        if not parents_path.exists():
            return CheckResult(
                name="parents_db",
                status="fail",
                message=f"{parents_path.name} not found"
            )
        
        try:
            conn = sqlite3.connect(parents_path)
            cursor = conn.cursor()
            
            # Check tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            if 'parents' not in tables:
                return CheckResult(
                    name="parents_db",
                    status="fail",
                    message="Missing 'parents' table in database"
                )
            
            # Count parents
            cursor.execute("SELECT COUNT(*) FROM parents")
            parent_count = cursor.fetchone()[0]
            
            # Count documents
            doc_count = 0
            if 'documents' in tables:
                cursor.execute("SELECT COUNT(*) FROM documents")
                doc_count = cursor.fetchone()[0]
            
            conn.close()
            
            self._log(f"Parents: {parent_count}")
            self._log(f"Documents: {doc_count}")
            
            return CheckResult(
                name="parents_db",
                status="pass",
                message=f"{parent_count} parents, {doc_count} docs",
                details={"parent_count": parent_count, "doc_count": doc_count, "tables": tables}
            )
            
        except Exception as e:
            return CheckResult(
                name="parents_db",
                status="fail",
                message=f"Failed to read {parents_path.name}: {e}"
            )
    
    def check_qdrant(self) -> CheckResult:
        """Validate Qdrant collection."""
        try:
            from qdrant_client import QdrantClient
            
            client = QdrantClient(path=str(self.config.paths.qdrant_dir))
            
            collections = client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.config.qdrant.collection_name not in collection_names:
                return CheckResult(
                    name="qdrant",
                    status="fail",
                    message=f"Collection '{self.config.qdrant.collection_name}' not found"
                )
            
            # Get collection info
            info = client.get_collection(self.config.qdrant.collection_name)
            vector_count = info.points_count
            vector_dim = info.config.params.vectors.size
            
            self._log(f"Vectors: {vector_count}")
            self._log(f"Dimension: {vector_dim}")
            
            # Check dimension matches config
            expected_dim = self.config.embedding.dimensions
            if vector_dim != expected_dim:
                return CheckResult(
                    name="qdrant",
                    status="fail",
                    message=f"Dimension mismatch: index={vector_dim}, config={expected_dim}",
                    details={"vector_count": vector_count, "dimension": vector_dim}
                )
            
            return CheckResult(
                name="qdrant",
                status="pass",
                message=f"{vector_count} vectors, dim={vector_dim}",
                details={"vector_count": vector_count, "dimension": vector_dim}
            )
            
        except Exception as e:
            return CheckResult(
                name="qdrant",
                status="fail",
                message=f"Qdrant check failed: {e}"
            )
    
    def check_id_consistency(self) -> CheckResult:
        """Check chunk IDs are consistent across indexes."""
        try:
            # Load chunk IDs from JSONL
            chunks_path = self.config.paths.chunks_jsonl_path
            jsonl_ids = set()
            
            with open(chunks_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        chunk = json.loads(line)
                        jsonl_ids.add(chunk.get('chunk_id', ''))
            
            # Load chunk IDs from BM25
            bm25_path = self.config.paths.bm25_index_path
            with open(bm25_path, 'rb') as f:
                bm25 = pickle.load(f)
            bm25_ids = set(bm25.chunk_ids) if hasattr(bm25, 'chunk_ids') else set()
            
            # Load chunk IDs from Qdrant mapping (stored under qdrant storage dir)
            mapping_path = self.config.paths.qdrant_dir / "id_mapping.json"
            qdrant_ids = set()
            if mapping_path.exists():
                with open(mapping_path, 'r') as f:
                    mapping = json.load(f)
                qdrant_ids = set(mapping.get('chunk_to_point', {}).keys())
            
            self._log(f"JSONL IDs: {len(jsonl_ids)}")
            self._log(f"BM25 IDs: {len(bm25_ids)}")
            self._log(f"Qdrant IDs: {len(qdrant_ids)}")
            
            # Check consistency
            issues = []
            
            if bm25_ids and jsonl_ids != bm25_ids:
                only_jsonl = jsonl_ids - bm25_ids
                only_bm25 = bm25_ids - jsonl_ids
                if only_jsonl:
                    issues.append(f"{len(only_jsonl)} IDs in JSONL but not BM25")
                if only_bm25:
                    issues.append(f"{len(only_bm25)} IDs in BM25 but not JSONL")
            
            if qdrant_ids and jsonl_ids != qdrant_ids:
                only_jsonl = jsonl_ids - qdrant_ids
                only_qdrant = qdrant_ids - jsonl_ids
                if only_jsonl:
                    issues.append(f"{len(only_jsonl)} IDs in JSONL but not Qdrant")
                if only_qdrant:
                    issues.append(f"{len(only_qdrant)} IDs in Qdrant but not JSONL")
            
            if issues:
                return CheckResult(
                    name="id_consistency",
                    status="fail",
                    message=f"ID mismatch: {issues[0]}",
                    details={"issues": issues}
                )
            
            return CheckResult(
                name="id_consistency",
                status="pass",
                message=f"All {len(jsonl_ids)} IDs consistent across indexes"
            )
            
        except Exception as e:
            return CheckResult(
                name="id_consistency",
                status="warn",
                message=f"Could not verify ID consistency: {e}"
            )
    
    def check_sample_query_latency(self) -> CheckResult:
        """Run a sample query and measure latency."""
        try:
            from .retrieve import Retriever
            
            retriever = Retriever()
            
            # Warm up
            _ = retriever.retrieve("test")
            
            # Timed query
            start = time.perf_counter()
            result = retriever.retrieve("example search query")
            latency_ms = (time.perf_counter() - start) * 1000
            
            self._log(f"Latency: {latency_ms:.0f}ms")
            self._log(f"Results: {len(result.chunks)}")
            
            if latency_ms > 3000:
                return CheckResult(
                    name="query_latency",
                    status="warn",
                    message=f"High latency: {latency_ms:.0f}ms (target: <3000ms)",
                    latency_ms=latency_ms
                )
            
            return CheckResult(
                name="query_latency",
                status="pass",
                message=f"Query latency: {latency_ms:.0f}ms",
                latency_ms=latency_ms,
                details={"result_count": len(result.chunks)}
            )
            
        except Exception as e:
            return CheckResult(
                name="query_latency",
                status="fail",
                message=f"Query test failed: {e}"
            )
    
    def check_lm_studio(self) -> CheckResult:
        """Check LM Studio connectivity."""
        try:
            from openai import OpenAI
            
            client = OpenAI(
                base_url=self.config.llm.base_url,
                api_key=self.config.llm.api_key,
                timeout=5.0
            )
            
            models = client.models.list()
            model_names = [m.id for m in models.data]
            
            self._log(f"Connected to {self.config.llm.base_url}")
            self._log(f"Models: {model_names}")
            
            if not model_names:
                return CheckResult(
                    name="lm_studio",
                    status="warn",
                    message="LM Studio running but no models loaded"
                )
            
            return CheckResult(
                name="lm_studio",
                status="pass",
                message=f"LM Studio connected, {len(model_names)} models available",
                details={"models": model_names}
            )
            
        except Exception as e:
            return CheckResult(
                name="lm_studio",
                status="warn",
                message=f"LM Studio not reachable: {e}"
            )
    
    # --------------------------------------------------------------------------
    # Run All Checks
    # --------------------------------------------------------------------------
    
    def run_all(self, quick: bool = False) -> HealthReport:
        """Run all health checks."""
        print("\n" + "=" * 60)
        print("RAG System v2 - Health Check")
        print("=" * 60)
        
        checks = [
            ("Files Exist", self.check_files_exist),
            ("Manifest", self.check_manifest),
            ("Chunks JSONL", self.check_chunks_jsonl),
            ("Alpha Concepts Chunks JSONL", self.check_alpha_concepts_chunks_jsonl),
            ("BM25 Index", self.check_bm25_index),
            ("Parents DB", self.check_parents_db),
            ("Qdrant", self.check_qdrant),
            ("ID Consistency", self.check_id_consistency),
        ]
        
        if not quick:
            checks.extend([
                ("Query Latency", self.check_sample_query_latency),
                ("LM Studio", self.check_lm_studio),
            ])
        
        for name, check_fn in checks:
            print(f"\n[{name}]")
            result = check_fn()
            self.report.add_check(result)
            
            status_icon = {"pass": "[+]", "warn": "[!]", "fail": "[x]"}[result.status]
            print(f"  {status_icon} {result.message}")
        
        self.report.finalize()
        
        # Summary
        print("\n" + "=" * 60)
        status_icon = {"healthy": "[+]", "degraded": "[!]", "unhealthy": "[x]"}[self.report.overall_status]
        print(f"OVERALL: {status_icon} {self.report.overall_status.upper()}")
        print(f"  Pass: {self.report.summary.get('pass', 0)}")
        print(f"  Warn: {self.report.summary.get('warn', 0)}")
        print(f"  Fail: {self.report.summary.get('fail', 0)}")
        print("=" * 60)
        
        return self.report


# ==============================================================================
# CLI
# ==============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG System v2 Health Check")
    parser.add_argument('--quick', action='store_true', help='Skip latency tests')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--json', type=Path, help='Save report to JSON file')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.WARNING)
    
    checker = HealthChecker(verbose=args.verbose)
    report = checker.run_all(quick=args.quick)
    
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nReport saved to {args.json}")
    
    # Exit code based on health
    if report.overall_status == "unhealthy":
        sys.exit(1)
    elif report.overall_status == "degraded":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
