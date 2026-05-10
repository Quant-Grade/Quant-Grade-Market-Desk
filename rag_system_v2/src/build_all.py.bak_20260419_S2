"""
build_all.py - Complete Index Build Orchestration
==================================================
Purpose: Single command to rebuild entire index pipeline from scratch.
         Ensures reproducible, atomic rebuilds with manifest verification.

Usage:
  # Full rebuild from docs
  python -m src.build_all --docs ./docs

  # Rebuild with verification
  python -m src.build_all --docs ./docs --verify

  # Clean rebuild (wipe existing data first)
  python -m src.build_all --docs ./docs --clean

Outputs:
  - data/chunks.jsonl (ingested chunks)
  - data/bm25_index.pkl (BM25 index)
  - data/qdrant/ (vector index)
  - data/parents.sqlite (parent chunks SQLite; see repo_paths.PARENTS_STORE_FILENAME)
  - data/manifest.json (integrity manifest)

Failure Modes:
  - Partial build detected → Rollback to previous state
  - Manifest mismatch → Abort with clear error
  - Missing dependencies → List what's needed
"""

import os
import sys
import json
import time
import shutil
import hashlib
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from .config import get_config
from .repo_paths import MANIFEST_FILENAME as _MANIFEST_FILENAME, PARENTS_STORE_FILENAME

logger = logging.getLogger(__name__)


# ==============================================================================
# MANIFEST MANAGEMENT
# ==============================================================================

SCHEMA_VERSION = 2

def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file."""
    if not path.exists():
        return ""
    
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_directory_hash(path: Path) -> str:
    """Compute hash of directory contents (sorted file list + sizes)."""
    if not path.exists():
        return ""
    
    entries = []
    for item in sorted(path.rglob('*')):
        if item.is_file():
            entries.append(f"{item.relative_to(path)}:{item.stat().st_size}")
    
    content = '\n'.join(entries)
    return hashlib.sha256(content.encode()).hexdigest()


class Manifest:
    """
    Build manifest for integrity verification.
    
    Tracks hashes of all index artifacts to detect:
    - Partial rebuilds
    - Version mismatches
    - Corrupted files
    """
    
    MANIFEST_FILE = _MANIFEST_FILENAME
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.manifest_path = data_dir / self.MANIFEST_FILE
        
    def create(
        self,
        chunks_path: Path,
        bm25_path: Path,
        qdrant_path: Path,
        parents_path: Path,
        embedding_model: str,
        chunk_count: int,
        doc_count: int
    ) -> Dict[str, Any]:
        """Create new manifest after successful build."""
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now().isoformat(),
            "embedding_model": embedding_model,
            "chunk_count": chunk_count,
            "doc_count": doc_count,
            "hashes": {
                "chunks_sha256": compute_file_hash(chunks_path),
                "bm25_index_sha256": compute_file_hash(bm25_path),
                "qdrant_collection_hash": compute_directory_hash(qdrant_path),
                "parents_sha256": compute_file_hash(parents_path)
            },
            "paths": {
                "chunks": str(chunks_path),
                "bm25": str(bm25_path),
                "qdrant": str(qdrant_path),
                "parents": str(parents_path)
            }
        }
        
        # Write atomically
        temp_path = self.manifest_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        temp_path.replace(self.manifest_path)
        
        logger.info(f"Manifest created: {self.manifest_path}")
        return manifest
    
    def load(self) -> Optional[Dict[str, Any]]:
        """Load existing manifest."""
        if not self.manifest_path.exists():
            return None
        
        with open(self.manifest_path, 'r') as f:
            return json.load(f)
    
    def verify(self) -> tuple[bool, list[str]]:
        """
        Verify current state matches manifest.
        
        Returns (is_valid, list_of_issues).
        """
        manifest = self.load()
        if manifest is None:
            return False, ["No manifest found"]
        
        issues = []
        
        # Check schema version
        if manifest.get("schema_version") != SCHEMA_VERSION:
            issues.append(f"Schema version mismatch: expected {SCHEMA_VERSION}, got {manifest.get('schema_version')}")
        
        # Check file hashes
        paths = manifest.get("paths", {})
        hashes = manifest.get("hashes", {})
        
        if paths.get("chunks"):
            current = compute_file_hash(Path(paths["chunks"]))
            expected = hashes.get("chunks_sha256", "")
            if current != expected:
                issues.append(f"chunks.jsonl hash mismatch")
        
        if paths.get("bm25"):
            current = compute_file_hash(Path(paths["bm25"]))
            expected = hashes.get("bm25_index_sha256", "")
            if current != expected:
                issues.append(f"bm25_index.pkl hash mismatch")
        
        if paths.get("qdrant"):
            current = compute_directory_hash(Path(paths["qdrant"]))
            expected = hashes.get("qdrant_collection_hash", "")
            if current != expected:
                issues.append(f"qdrant collection hash mismatch")
        
        if paths.get("parents"):
            current = compute_file_hash(Path(paths["parents"]))
            expected = hashes.get("parents_sha256", "")
            if current != expected:
                issues.append(f"{PARENTS_STORE_FILENAME} hash mismatch")
        
        return len(issues) == 0, issues


# ==============================================================================
# BUILD ORCHESTRATOR
# ==============================================================================

class BuildOrchestrator:
    """
    Orchestrates full index build pipeline.
    
    Steps:
    1. Verify prerequisites
    2. Backup existing data (if any)
    3. Ingest documents → chunks.jsonl
    4. Build BM25 index
    5. Build Qdrant index
    6. Create manifest
    7. Verify integrity
    8. Clean up backup (or rollback on failure)
    """
    
    def __init__(self, docs_path: Path, clean: bool = False):
        self.config = get_config()
        self.docs_path = docs_path
        self.clean = clean
        
        # Paths
        self.data_dir = self.config.paths.data_dir
        self.chunks_path = self.data_dir / "chunks.jsonl"
        self.bm25_path = self.data_dir / "bm25_index.pkl"
        self.qdrant_path = self.config.paths.qdrant_dir
        self.parents_path = self.config.paths.parents_db_path
        self.backup_dir = self.data_dir / "_backup"
        
        self.manifest = Manifest(self.data_dir)
        
    def _check_prerequisites(self) -> list[str]:
        """Check all prerequisites are met."""
        issues = []
        
        if not self.docs_path.exists():
            issues.append(f"Docs path does not exist: {self.docs_path}")
        elif not any(self.docs_path.iterdir()):
            issues.append(f"Docs path is empty: {self.docs_path}")
        
        # Check imports work
        try:
            from .ingest import Ingester
            from .index_bm25 import BM25Index
            from .index_qdrant import build_qdrant_index
        except ImportError as e:
            issues.append(f"Missing dependency: {e}")
        
        return issues
    
    def _backup_existing(self):
        """Backup existing data before rebuild."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        for path in [self.chunks_path, self.bm25_path, self.parents_path]:
            if path.exists():
                shutil.copy2(path, self.backup_dir / path.name)
        
        if self.qdrant_path.exists():
            shutil.copytree(self.qdrant_path, self.backup_dir / "qdrant")
        
        manifest_path = self.data_dir / _MANIFEST_FILENAME
        if manifest_path.exists():
            shutil.copy2(manifest_path, self.backup_dir / _MANIFEST_FILENAME)
        
        logger.info(f"Backed up existing data to {self.backup_dir}")
    
    def _rollback(self):
        """Rollback to backup on failure."""
        if not self.backup_dir.exists():
            logger.warning("No backup to rollback to")
            return
        
        # Remove failed build artifacts
        for path in [self.chunks_path, self.bm25_path, self.parents_path]:
            if path.exists():
                path.unlink()
        
        if self.qdrant_path.exists():
            shutil.rmtree(self.qdrant_path)
        
        # Restore from backup
        for item in self.backup_dir.iterdir():
            dest = self.data_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        
        logger.info("Rolled back to previous state")
    
    def _cleanup_backup(self):
        """Remove backup after successful build."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
            logger.info("Cleaned up backup")
    
    def _clean_existing(self):
        """Remove all existing data."""
        for path in [self.chunks_path, self.bm25_path, self.parents_path]:
            if path.exists():
                path.unlink()
        
        if self.qdrant_path.exists():
            shutil.rmtree(self.qdrant_path)
        
        manifest_path = self.data_dir / _MANIFEST_FILENAME
        if manifest_path.exists():
            manifest_path.unlink()
        
        logger.info("Cleaned existing data")
    
    def build(self, verify: bool = True) -> bool:
        """
        Run full build pipeline.
        
        Returns True on success, False on failure.
        """
        print("=" * 60)
        print("RAG System v2 - Full Index Build")
        print("=" * 60)
        
        start_time = time.perf_counter()
        
        # Step 1: Prerequisites
        print("\n[1/7] Checking prerequisites...")
        issues = self._check_prerequisites()
        if issues:
            for issue in issues:
                print(f"  ✗ {issue}")
            return False
        print("  ✓ All prerequisites met")
        
        # Step 2: Backup or clean
        if self.clean:
            print("\n[2/7] Cleaning existing data...")
            self._clean_existing()
        else:
            print("\n[2/7] Backing up existing data...")
            self._backup_existing()
        
        try:
            # Step 3: Ingest
            print("\n[3/7] Ingesting documents...")
            from .ingest import Ingester, ingest_to_jsonl
            
            chunk_count, doc_count = ingest_to_jsonl(
                docs_dir=self.docs_path,
                output_path=self.chunks_path
            )
            print(f"  ✓ Ingested {doc_count} docs → {chunk_count} chunks")
            
            # Step 4: Build BM25
            print("\n[4/7] Building BM25 index...")
            from .index_bm25 import build_bm25_from_jsonl
            
            bm25_count = build_bm25_from_jsonl(
                chunks_path=self.chunks_path,
                output_path=self.bm25_path
            )
            print(f"  ✓ BM25 index: {bm25_count} chunks")
            
            # Step 5: Build Qdrant
            print("\n[5/7] Building Qdrant index...")
            from .index_qdrant import build_qdrant_index
            
            cache_dir = self.data_dir / "embedding_cache"
            qdrant_index = build_qdrant_index(
                chunks_path=self.chunks_path,
                qdrant_path=self.qdrant_path,
                model_name=self.config.embedding.model,
                collection_name=self.config.qdrant.collection_name,
                cache_dir=cache_dir,
                batch_size=self.config.embedding.batch_size,
            )
            qdrant_count = qdrant_index.count()
            print(f"  ✓ Qdrant index: {qdrant_count} vectors")
            
            # Step 6: Create manifest
            print("\n[6/7] Creating manifest...")
            manifest = self.manifest.create(
                chunks_path=self.chunks_path,
                bm25_path=self.bm25_path,
                qdrant_path=self.qdrant_path,
                parents_path=self.parents_path,
                embedding_model=self.config.embedding.model,
                chunk_count=chunk_count,
                doc_count=doc_count
            )
            print(f"  ✓ Manifest created (schema v{SCHEMA_VERSION})")
            
            # Step 7: Verify
            if verify:
                print("\n[7/7] Verifying integrity...")
                is_valid, issues = self.manifest.verify()
                if not is_valid:
                    for issue in issues:
                        print(f"  ✗ {issue}")
                    raise RuntimeError("Manifest verification failed")
                print("  ✓ All hashes verified")
            else:
                print("\n[7/7] Skipping verification (--no-verify)")
            
            # Success - cleanup backup
            self._cleanup_backup()
            
            elapsed = time.perf_counter() - start_time
            print("\n" + "=" * 60)
            print(f"BUILD COMPLETE in {elapsed:.1f}s")
            print(f"  Docs:   {doc_count}")
            print(f"  Chunks: {chunk_count}")
            print(f"  Model:  {self.config.embedding.model}")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            logger.exception("Build failed")
            print(f"\n✗ BUILD FAILED: {e}")
            
            if not self.clean:
                print("Rolling back to previous state...")
                self._rollback()
            
            return False


# ==============================================================================
# CLI
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="RAG System v2 - Full Index Build")
    parser.add_argument('--docs', type=Path, required=True, help='Path to documents directory')
    parser.add_argument('--clean', action='store_true', help='Clean existing data before build')
    parser.add_argument('--no-verify', action='store_true', help='Skip manifest verification')
    parser.add_argument('--verify-only', action='store_true', help='Only verify existing manifest')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    config = get_config()
    
    if args.verify_only:
        print("Verifying existing manifest...")
        manifest = Manifest(config.paths.data_dir)
        is_valid, issues = manifest.verify()
        
        if is_valid:
            print("✓ Manifest verification passed")
            loaded = manifest.load()
            print(f"  Schema:  v{loaded.get('schema_version')}")
            print(f"  Chunks:  {loaded.get('chunk_count')}")
            print(f"  Model:   {loaded.get('embedding_model')}")
            print(f"  Created: {loaded.get('created_at')}")
            sys.exit(0)
        else:
            print("✗ Manifest verification failed:")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
    
    orchestrator = BuildOrchestrator(
        docs_path=args.docs,
        clean=args.clean
    )
    
    success = orchestrator.build(verify=not args.no_verify)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
