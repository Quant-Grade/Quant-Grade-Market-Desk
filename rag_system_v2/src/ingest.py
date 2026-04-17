"""
RAG System V2 - Document Ingestion Module
=========================================
Purpose: Parse docs, create parent-child chunks, dedupe, extract metadata
Inputs: Directory of documents (PDF, MD, TXT, code files)
Outputs: Parent chunks (stored in SQLite), Child chunks (indexed in Qdrant/BM25)
Failure modes: 
  - Corrupt PDF → log error, skip file
  - Encoding issues → fallback to utf-8 with replace
  - Empty chunks → filter out
  - Duplicate docs → skip via SHA-256
Logging: INFO for file processing, WARN for skips, ERROR for failures

PARENT-CHILD ARCHITECTURE:
- Parents: 900-1200 tokens, preserve semantic boundaries
- Children: 200-350 tokens with overlap, indexed for retrieval
- At query time: retrieve children, expand to parents for context
"""

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)


class FileType(Enum):
    """Supported file types."""
    PDF = "pdf"
    MARKDOWN = "md"
    TEXT = "txt"
    PYTHON = "py"
    JAVASCRIPT = "js"
    TYPESCRIPT = "ts"
    JSON_FILE = "json"
    YAML = "yaml"
    HTML = "html"
    UNKNOWN = "unknown"


@dataclass
class DocumentMetadata:
    """Metadata for a source document."""
    doc_id: str  # SHA-256 of normalized content
    source_path: str
    file_type: str
    file_name: str
    modified_time: str
    file_size_bytes: int
    title: Optional[str] = None
    total_pages: Optional[int] = None  # For PDFs


@dataclass
class ParentChunk:
    """
    Parent chunk - larger context unit.
    Stored in SQLite for retrieval expansion.
    """
    parent_id: str  # SHA-256 of normalized parent text
    doc_id: str
    parent_index: int  # Position in document
    text_original: str  # Original text for citation
    text_normalized: str  # Normalized for dedup/matching
    char_start: int
    char_end: int
    page_num: Optional[int] = None  # For PDFs
    section_headers: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)


@dataclass
class ChildChunk:
    """
    Child chunk - indexed unit for retrieval.
    Stored in Qdrant (vectors) and BM25 (lexical).
    """
    chunk_id: str  # Stable ID: hash of doc_id + parent_index + child_index
    chunk_hash: str  # SHA-256 of normalized text (for dedup)
    doc_id: str
    parent_id: str
    child_index: int  # Position within parent
    text_original: str
    text_normalized: str
    char_start: int  # Relative to document
    char_end: int
    source_path: str
    file_type: str
    page_num: Optional[int] = None
    section_headers: List[str] = field(default_factory=list)


# ============================================================================
# TEXT NORMALIZATION
# ============================================================================

def normalize_text(text: str) -> str:
    """
    Normalize text for deduplication and BM25 tokenization.
    Preserves meaning while removing noise.
    
    DOES NOT modify original text - normalization is for matching only.
    """
    if not text:
        return ""
    
    # Convert to lowercase
    normalized = text.lower()
    
    # Normalize whitespace (collapse multiple spaces, normalize newlines)
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove zero-width characters
    normalized = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', normalized)
    
    # Normalize unicode (NFD -> NFC)
    import unicodedata
    normalized = unicodedata.normalize('NFC', normalized)
    
    # Strip leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized


def compute_hash(text: str) -> str:
    """Compute SHA-256 hash of text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def compute_stable_chunk_id(doc_id: str, parent_index: int, child_index: int) -> str:
    """
    Generate stable chunk ID that survives rebuilds.
    Format: {doc_hash_prefix}:{parent_idx}:{child_idx}
    """
    combined = f"{doc_id}:{parent_index}:{child_index}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:12]


# ============================================================================
# FILE PARSING
# ============================================================================

def detect_file_type(path: Path) -> FileType:
    """Detect file type from extension."""
    ext = path.suffix.lower().lstrip('.')
    mapping = {
        'pdf': FileType.PDF,
        'md': FileType.MARKDOWN,
        'markdown': FileType.MARKDOWN,
        'txt': FileType.TEXT,
        'text': FileType.TEXT,
        'py': FileType.PYTHON,
        'js': FileType.JAVASCRIPT,
        'ts': FileType.TYPESCRIPT,
        'tsx': FileType.TYPESCRIPT,
        'jsx': FileType.JAVASCRIPT,
        'json': FileType.JSON_FILE,
        'yaml': FileType.YAML,
        'yml': FileType.YAML,
        'html': FileType.HTML,
        'htm': FileType.HTML,
    }
    return mapping.get(ext, FileType.UNKNOWN)


def parse_pdf(path: Path) -> Tuple[str, Dict[str, Any]]:
    """
    Parse PDF using PyMuPDF (fitz).
    Returns (text_content, metadata_dict).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install PyMuPDF")
        raise ImportError("PyMuPDF required for PDF parsing")
    
    text_parts = []
    metadata = {"pages": [], "total_pages": 0}
    
    try:
        doc = fitz.open(path)
        metadata["total_pages"] = len(doc)
        
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text("text")
            if page_text.strip():
                # Mark page boundaries for later chunking
                text_parts.append(f"\n[PAGE:{page_num}]\n{page_text}")
                metadata["pages"].append({
                    "page_num": page_num,
                    "char_start": sum(len(p) for p in text_parts[:-1]),
                    "char_end": sum(len(p) for p in text_parts)
                })
        
        doc.close()
        return "".join(text_parts), metadata
        
    except Exception as e:
        logger.error(f"PDF parse error for {path}: {e}")
        raise


def parse_markdown(path: Path) -> Tuple[str, Dict[str, Any]]:
    """
    Parse Markdown, extracting headers for metadata.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Markdown read error for {path}: {e}")
        raise
    
    # Extract headers for section tracking
    header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    headers = [(m.start(), len(m.group(1)), m.group(2)) 
               for m in header_pattern.finditer(content)]
    
    metadata = {
        "headers": headers,
        "title": headers[0][2] if headers else None
    }
    
    return content, metadata


def parse_code(path: Path) -> Tuple[str, Dict[str, Any]]:
    """
    Parse code files, extracting function/class definitions.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Code read error for {path}: {e}")
        raise
    
    # Basic extraction of definitions (Python-focused, extend as needed)
    def_pattern = re.compile(r'^(class|def|async def)\s+(\w+)', re.MULTILINE)
    definitions = [(m.start(), m.group(1), m.group(2)) 
                   for m in def_pattern.finditer(content)]
    
    metadata = {
        "definitions": definitions,
        "language": path.suffix.lstrip('.')
    }
    
    return content, metadata


def parse_text(path: Path) -> Tuple[str, Dict[str, Any]]:
    """Parse plain text file."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Text read error for {path}: {e}")
        raise
    
    return content, {}


def parse_document(path: Path) -> Tuple[str, Dict[str, Any], FileType]:
    """
    Parse document based on type.
    Returns (content, metadata, file_type).
    """
    file_type = detect_file_type(path)
    
    parsers = {
        FileType.PDF: parse_pdf,
        FileType.MARKDOWN: parse_markdown,
        FileType.TEXT: parse_text,
        FileType.PYTHON: parse_code,
        FileType.JAVASCRIPT: parse_code,
        FileType.TYPESCRIPT: parse_code,
        FileType.JSON_FILE: parse_text,
        FileType.YAML: parse_text,
        FileType.HTML: parse_text,
    }
    
    parser = parsers.get(file_type, parse_text)
    content, metadata = parser(path)
    
    return content, metadata, file_type


# ============================================================================
# CHUNKING - PARENT-CHILD ARCHITECTURE
# ============================================================================

class Chunker:
    """
    Parent-child chunking with semantic boundary awareness.
    
    Strategy:
    1. Split document into semantic sections (headers, pages, functions)
    2. Group sections into parent chunks (900-1200 tokens)
    3. Split parents into overlapping child chunks (200-350 tokens)
    """
    
    def __init__(
        self,
        parent_target_chars: int = 4000,
        parent_max_chars: int = 4800,
        parent_min_chars: int = 3600,
        child_target_chars: int = 1100,
        child_max_chars: int = 1400,
        child_min_chars: int = 800,
        child_overlap_chars: int = 200,
    ):
        self.parent_target = parent_target_chars
        self.parent_max = parent_max_chars
        self.parent_min = parent_min_chars
        self.child_target = child_target_chars
        self.child_max = child_max_chars
        self.child_min = child_min_chars
        self.child_overlap = child_overlap_chars
    
    def _find_semantic_breaks(
        self, 
        text: str, 
        file_type: FileType
    ) -> List[int]:
        """
        Find positions of semantic breaks in text.
        Returns sorted list of character positions.
        """
        breaks = set()
        breaks.add(0)
        breaks.add(len(text))
        
        # Common breaks: double newlines (paragraphs)
        for m in re.finditer(r'\n\n+', text):
            breaks.add(m.start())
        
        # Markdown headers
        if file_type == FileType.MARKDOWN:
            for m in re.finditer(r'\n#{1,6}\s+', text):
                breaks.add(m.start())
        
        # PDF page markers
        if file_type == FileType.PDF:
            for m in re.finditer(r'\[PAGE:\d+\]', text):
                breaks.add(m.start())
        
        # Code function/class definitions
        if file_type in (FileType.PYTHON, FileType.JAVASCRIPT, FileType.TYPESCRIPT):
            for m in re.finditer(r'\n(class|def|function|async def|async function)\s+', text):
                breaks.add(m.start())
        
        return sorted(breaks)
    
    def _find_sentence_break(self, text: str, start: int, end: int) -> int:
        """
        Find best sentence break point between start and end.
        Prefers: sentence end > clause end > word end
        """
        search_text = text[start:end]
        
        # Try sentence endings
        for pattern in [r'[.!?]\s+', r'[.!?]$', r':\s*\n', r';\s+']:
            matches = list(re.finditer(pattern, search_text))
            if matches:
                return start + matches[-1].end()
        
        # Try comma/clause breaks
        for pattern in [r',\s+', r'\)\s+', r'\]\s+']:
            matches = list(re.finditer(pattern, search_text))
            if matches:
                return start + matches[-1].end()
        
        # Fall back to word boundary
        matches = list(re.finditer(r'\s+', search_text))
        if matches:
            return start + matches[-1].end()
        
        return end
    
    def create_parents(
        self,
        text: str,
        file_type: FileType,
        metadata: Dict[str, Any]
    ) -> List[Tuple[str, int, int, List[str]]]:
        """
        Create parent chunks from document text.
        Returns: List of (text, char_start, char_end, section_headers)
        """
        if not text.strip():
            return []
        
        breaks = self._find_semantic_breaks(text, file_type)
        parents = []
        current_start = 0
        current_headers: List[str] = []
        
        # Track current headers from markdown
        if file_type == FileType.MARKDOWN and "headers" in metadata:
            header_positions = {h[0]: h[2] for h in metadata["headers"]}
        else:
            header_positions = {}
        
        i = 0
        while i < len(breaks) - 1:
            # Try to build a parent chunk of target size
            chunk_end = current_start
            
            # Accumulate until we reach target size
            while i < len(breaks) - 1:
                next_break = breaks[i + 1]
                potential_size = next_break - current_start
                
                # Update headers if we pass one
                for pos, header in header_positions.items():
                    if current_start <= pos < next_break and header not in current_headers:
                        current_headers = [header]  # Reset to most recent header
                
                if potential_size <= self.parent_target:
                    chunk_end = next_break
                    i += 1
                elif potential_size <= self.parent_max:
                    chunk_end = next_break
                    i += 1
                    break  # At max, stop here
                else:
                    if chunk_end == current_start:
                        # Single section too big, force split
                        chunk_end = self._find_sentence_break(
                            text, 
                            current_start + self.parent_min,
                            min(current_start + self.parent_target, next_break)
                        )
                    break
            
            # Extract parent chunk
            if chunk_end > current_start:
                parent_text = text[current_start:chunk_end].strip()
                if len(parent_text) >= self.parent_min // 2:  # Don't create tiny chunks
                    parents.append((
                        parent_text,
                        current_start,
                        chunk_end,
                        list(current_headers)
                    ))
                current_start = chunk_end
            else:
                i += 1
        
        # Handle remaining text
        if current_start < len(text):
            remaining = text[current_start:].strip()
            if remaining and len(remaining) >= self.parent_min // 4:
                # Merge with previous if too small
                if parents and len(remaining) < self.parent_min // 2:
                    prev_text, prev_start, _, prev_headers = parents[-1]
                    parents[-1] = (
                        prev_text + "\n\n" + remaining,
                        prev_start,
                        len(text),
                        prev_headers
                    )
                else:
                    parents.append((remaining, current_start, len(text), current_headers))
        
        return parents
    
    def create_children(
        self,
        parent_text: str,
        parent_char_start: int
    ) -> List[Tuple[str, int, int]]:
        """
        Create overlapping child chunks from parent text.
        Returns: List of (text, char_start_relative_to_doc, char_end_relative_to_doc)
        """
        if not parent_text.strip():
            return []
        
        children = []
        current_start = 0
        
        while current_start < len(parent_text):
            # Calculate end position
            ideal_end = current_start + self.child_target
            max_end = min(current_start + self.child_max, len(parent_text))
            
            if ideal_end >= len(parent_text):
                # Last chunk - take all remaining
                chunk_end = len(parent_text)
            else:
                # Find good break point
                chunk_end = self._find_sentence_break(
                    parent_text,
                    current_start + self.child_min,
                    max_end
                )
            
            # Extract child chunk
            child_text = parent_text[current_start:chunk_end].strip()
            if child_text:
                children.append((
                    child_text,
                    parent_char_start + current_start,
                    parent_char_start + chunk_end
                ))
            
            # Move forward with overlap
            current_start = chunk_end - self.child_overlap
            if current_start <= 0 or chunk_end >= len(parent_text):
                break
        
        return children


# ============================================================================
# PARENT STORAGE (SQLite)
# ============================================================================

class ParentStore:
    """SQLite storage for parent chunks."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parents (
                parent_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                parent_index INTEGER NOT NULL,
                text_original TEXT NOT NULL,
                text_normalized TEXT NOT NULL,
                char_start INTEGER,
                char_end INTEGER,
                page_num INTEGER,
                section_headers TEXT,
                child_ids TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_parents_doc_id ON parents(doc_id)
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                file_type TEXT,
                file_name TEXT,
                modified_time TEXT,
                file_size_bytes INTEGER,
                title TEXT,
                total_pages INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def store_document(self, meta: DocumentMetadata) -> bool:
        """
        Store document metadata.
        Returns True if new, False if duplicate.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check for existing
        cursor.execute("SELECT doc_id FROM documents WHERE doc_id = ?", (meta.doc_id,))
        if cursor.fetchone():
            conn.close()
            return False  # Duplicate
        
        cursor.execute("""
            INSERT INTO documents 
            (doc_id, source_path, file_type, file_name, modified_time, 
             file_size_bytes, title, total_pages)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meta.doc_id, meta.source_path, meta.file_type, meta.file_name,
            meta.modified_time, meta.file_size_bytes, meta.title, meta.total_pages
        ))
        
        conn.commit()
        conn.close()
        return True
    
    def store_parent(self, parent: ParentChunk) -> bool:
        """
        Store parent chunk.
        Returns True if new, False if duplicate.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check for existing
        cursor.execute("SELECT parent_id FROM parents WHERE parent_id = ?", 
                       (parent.parent_id,))
        if cursor.fetchone():
            conn.close()
            return False  # Duplicate
        
        cursor.execute("""
            INSERT INTO parents
            (parent_id, doc_id, parent_index, text_original, text_normalized,
             char_start, char_end, page_num, section_headers, child_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parent.parent_id, parent.doc_id, parent.parent_index,
            parent.text_original, parent.text_normalized,
            parent.char_start, parent.char_end, parent.page_num,
            json.dumps(parent.section_headers),
            json.dumps(parent.child_ids)
        ))
        
        conn.commit()
        conn.close()
        return True
    
    def get_parent(self, parent_id: str) -> Optional[ParentChunk]:
        """Retrieve parent chunk by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT parent_id, doc_id, parent_index, text_original, text_normalized,
                   char_start, char_end, page_num, section_headers, child_ids
            FROM parents WHERE parent_id = ?
        """, (parent_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return ParentChunk(
            parent_id=row[0],
            doc_id=row[1],
            parent_index=row[2],
            text_original=row[3],
            text_normalized=row[4],
            char_start=row[5],
            char_end=row[6],
            page_num=row[7],
            section_headers=json.loads(row[8]) if row[8] else [],
            child_ids=json.loads(row[9]) if row[9] else []
        )
    
    def get_parents_by_doc(self, doc_id: str) -> List[ParentChunk]:
        """Get all parents for a document."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT parent_id, doc_id, parent_index, text_original, text_normalized,
                   char_start, char_end, page_num, section_headers, child_ids
            FROM parents WHERE doc_id = ? ORDER BY parent_index
        """, (doc_id,))
        
        parents = []
        for row in cursor.fetchall():
            parents.append(ParentChunk(
                parent_id=row[0],
                doc_id=row[1],
                parent_index=row[2],
                text_original=row[3],
                text_normalized=row[4],
                char_start=row[5],
                char_end=row[6],
                page_num=row[7],
                section_headers=json.loads(row[8]) if row[8] else [],
                child_ids=json.loads(row[9]) if row[9] else []
            ))
        
        conn.close()
        return parents
    
    def document_exists(self, doc_id: str) -> bool:
        """Check if document already ingested."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists


# ============================================================================
# MAIN INGESTION PIPELINE
# ============================================================================

class Ingester:
    """Main document ingestion pipeline."""
    
    def __init__(self, config=None):
        from .config import get_config
        self.config = config or get_config()
        self.chunker = Chunker(
            parent_target_chars=self.config.chunking.parent_target_tokens * 4,
            parent_max_chars=self.config.chunking.parent_max_tokens * 4,
            parent_min_chars=self.config.chunking.parent_min_tokens * 4,
            child_target_chars=self.config.chunking.child_target_tokens * 4,
            child_max_chars=self.config.chunking.child_max_tokens * 4,
            child_min_chars=self.config.chunking.child_min_tokens * 4,
            child_overlap_chars=self.config.chunking.child_overlap_tokens * 4,
        )
        self.parent_store = ParentStore(self.config.paths.parents_db_path)
        self._seen_chunk_hashes: set = set()
    
    def _extract_page_num(self, text: str, char_pos: int) -> Optional[int]:
        """Extract page number from PDF page markers."""
        # Look backwards for nearest [PAGE:N] marker
        search_text = text[:char_pos]
        matches = list(re.finditer(r'\[PAGE:(\d+)\]', search_text))
        if matches:
            return int(matches[-1].group(1))
        return None
    
    def ingest_file(self, path: Path) -> Generator[ChildChunk, None, None]:
        """
        Ingest single file, yield child chunks for indexing.
        Parent chunks are stored in SQLite automatically.
        """
        logger.info(f"Ingesting: {path}")
        
        try:
            # Parse document
            content, metadata, file_type = parse_document(path)
            
            if not content.strip():
                logger.warning(f"Empty content: {path}")
                return
            
            # Compute document hash for deduplication
            normalized_content = normalize_text(content)
            doc_id = compute_hash(normalized_content)
            
            # Check for duplicate document
            if self.parent_store.document_exists(doc_id):
                logger.info(f"Duplicate document skipped: {path}")
                return
            
            # Store document metadata
            doc_meta = DocumentMetadata(
                doc_id=doc_id,
                source_path=str(path),
                file_type=file_type.value,
                file_name=path.name,
                modified_time=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                file_size_bytes=path.stat().st_size,
                title=metadata.get("title"),
                total_pages=metadata.get("total_pages")
            )
            self.parent_store.store_document(doc_meta)
            
            # Create parent chunks
            parents = self.chunker.create_parents(content, file_type, metadata)
            
            for parent_idx, (parent_text, char_start, char_end, headers) in enumerate(parents):
                # Create parent
                parent_normalized = normalize_text(parent_text)
                parent_id = compute_hash(parent_normalized)
                
                # Extract page number for PDFs
                page_num = None
                if file_type == FileType.PDF:
                    page_num = self._extract_page_num(content, char_start)
                
                # Create child chunks from this parent
                children = self.chunker.create_children(parent_text, char_start)
                child_chunks = []
                
                for child_idx, (child_text, child_start, child_end) in enumerate(children):
                    child_normalized = normalize_text(child_text)
                    chunk_hash = compute_hash(child_normalized)
                    
                    # Skip duplicate chunks (e.g., repeated boilerplate)
                    if chunk_hash in self._seen_chunk_hashes:
                        logger.debug(f"Duplicate chunk skipped: {chunk_hash[:8]}")
                        continue
                    self._seen_chunk_hashes.add(chunk_hash)
                    
                    # Generate stable chunk ID
                    chunk_id = compute_stable_chunk_id(doc_id, parent_idx, child_idx)
                    
                    child_chunk = ChildChunk(
                        chunk_id=chunk_id,
                        chunk_hash=chunk_hash,
                        doc_id=doc_id,
                        parent_id=parent_id,
                        child_index=child_idx,
                        text_original=child_text,
                        text_normalized=child_normalized,
                        char_start=child_start,
                        char_end=child_end,
                        source_path=str(path),
                        file_type=file_type.value,
                        page_num=page_num,
                        section_headers=headers
                    )
                    
                    child_chunks.append(child_chunk)
                    yield child_chunk
                
                # Store parent with child IDs
                parent_chunk = ParentChunk(
                    parent_id=parent_id,
                    doc_id=doc_id,
                    parent_index=parent_idx,
                    text_original=parent_text,
                    text_normalized=parent_normalized,
                    char_start=char_start,
                    char_end=char_end,
                    page_num=page_num,
                    section_headers=headers,
                    child_ids=[c.chunk_id for c in child_chunks]
                )
                self.parent_store.store_parent(parent_chunk)
            
            logger.info(f"Ingested {path}: {len(parents)} parents")
            
        except Exception as e:
            logger.error(f"Failed to ingest {path}: {e}", exc_info=True)
    
    def ingest_directory(
        self, 
        directory: Path,
        extensions: Optional[List[str]] = None
    ) -> Generator[ChildChunk, None, None]:
        """
        Recursively ingest all files in directory.
        
        Args:
            directory: Root directory to scan
            extensions: Allowed extensions (default: all supported)
        """
        if extensions is None:
            extensions = ['pdf', 'md', 'txt', 'py', 'js', 'ts', 'json', 'yaml', 'yml', 'html']
        
        extensions = [ext.lstrip('.').lower() for ext in extensions]
        
        for path in directory.rglob('*'):
            if path.is_file() and path.suffix.lstrip('.').lower() in extensions:
                yield from self.ingest_file(path)


SCHEMA_VERSION = 2  # Increment when chunk format changes


def ingest_to_jsonl(
    docs_dir: Path,
    output_path: Path,
    config=None
) -> Tuple[int, int]:
    """
    Convenience function: ingest directory and write chunks to JSONL.
    
    Uses ATOMIC WRITES: writes to .tmp file, then renames on success.
    This prevents half-written files on crash.
    
    Returns (chunk_count, doc_count).
    """
    ingester = Ingester(config)
    chunk_count = 0
    doc_ids = set()
    
    # Write to temp file first (atomic write pattern)
    temp_path = output_path.with_suffix('.jsonl.tmp')
    
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            for chunk in ingester.ingest_directory(docs_dir):
                # Add schema version to each chunk for format drift detection
                chunk_dict = asdict(chunk)
                chunk_dict['schema_version'] = SCHEMA_VERSION
                f.write(json.dumps(chunk_dict) + '\n')
                chunk_count += 1
                doc_ids.add(chunk.doc_id)
        
        # Atomic rename (on POSIX this is atomic; on Windows it replaces)
        temp_path.replace(output_path)
        
        doc_count = len(doc_ids)
        logger.info(f"Wrote {chunk_count} chunks from {doc_count} docs to {output_path}")
        return chunk_count, doc_count
        
    except Exception as e:
        # Clean up temp file on failure
        if temp_path.exists():
            temp_path.unlink()
        raise


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import argparse
    import sys
    
    # Add parent directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description="Ingest documents into RAG system")
    parser.add_argument("input_dir", type=Path, help="Directory containing documents")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output JSONL path (default: data/chunks.jsonl)")
    parser.add_argument("--extensions", "-e", nargs="+", default=None,
                        help="File extensions to process")
    
    args = parser.parse_args()
    
    from config import get_config
    config = get_config()
    
    output_path = args.output or config.paths.chunks_jsonl_path
    
    chunk_count, doc_count = ingest_to_jsonl(args.input_dir, output_path, config)
    print(f"✓ Ingested {doc_count} docs → {chunk_count} chunks to {output_path}")
