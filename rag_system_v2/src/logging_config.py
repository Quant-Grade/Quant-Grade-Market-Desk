"""
logging_config.py - Structured Logging Configuration
=====================================================
Purpose: Centralized logging setup with rotation, structured JSON output,
         and per-module level control.

Usage:
  from src.logging_config import setup_logging
  setup_logging()  # Call once at startup

Features:
  - File rotation (10MB max, 5 backups)
  - Structured JSON logs for machine parsing
  - Console output with human-readable format
  - Per-stage fields: {stage, module, latency_ms, status}
  - Separate error log for quick debugging
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


# ==============================================================================
# STRUCTURED JSON FORMATTER
# ==============================================================================

class StructuredFormatter(logging.Formatter):
    """
    Formats log records as structured JSON for machine parsing.
    
    Output format:
    {
        "timestamp": "2026-01-07T12:34:56.789",
        "level": "INFO",
        "module": "retrieve",
        "stage": "vector_search",
        "message": "Searched 1000 vectors",
        "latency_ms": 45.2,
        "status": "success",
        "extra": {...}
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # Base fields
        log_dict = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage()
        }
        
        # Add stage/latency/status if present in extra
        for field in ['stage', 'latency_ms', 'status', 'query', 'chunk_count', 
                      'decision', 'trace_id', 'error']:
            if hasattr(record, field):
                log_dict[field] = getattr(record, field)
        
        # Add exception info if present
        if record.exc_info:
            log_dict['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_dict, default=str)


class ReadableFormatter(logging.Formatter):
    """Human-readable format for console output."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Color codes for different levels
        colors = {
            'DEBUG': '\033[36m',     # Cyan
            'INFO': '\033[32m',      # Green
            'WARNING': '\033[33m',   # Yellow
            'ERROR': '\033[31m',     # Red
            'CRITICAL': '\033[35m',  # Magenta
        }
        reset = '\033[0m'
        
        color = colors.get(record.levelname, '')
        
        # Format: [TIME] LEVEL module: message
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        base = f"[{timestamp}] {color}{record.levelname:8}{reset} {record.module}: {record.getMessage()}"
        
        # Add latency if present
        if hasattr(record, 'latency_ms'):
            base += f" ({record.latency_ms:.0f}ms)"
        
        # Add stage if present
        if hasattr(record, 'stage'):
            base = f"[{timestamp}] {color}{record.levelname:8}{reset} [{record.stage}] {record.getMessage()}"
        
        return base


# ==============================================================================
# LOGGING CONTEXT ADAPTER
# ==============================================================================

class StageLogAdapter(logging.LoggerAdapter):
    """
    Adapter that adds stage context to all log messages.
    
    Usage:
        logger = StageLogAdapter(logging.getLogger(__name__), stage="retrieve")
        logger.info("Found results", extra={"latency_ms": 45.2})
    """
    
    def __init__(self, logger: logging.Logger, stage: str):
        super().__init__(logger, {"stage": stage})
    
    def process(self, msg, kwargs):
        # Merge stage into extra
        extra = kwargs.get("extra", {})
        extra["stage"] = self.extra["stage"]
        kwargs["extra"] = extra
        return msg, kwargs


def get_stage_logger(module_name: str, stage: str) -> StageLogAdapter:
    """Get a logger with stage context pre-attached."""
    return StageLogAdapter(logging.getLogger(module_name), stage=stage)


# ==============================================================================
# STRUCTURED LOG HELPER
# ==============================================================================

def log_structured(
    logger: logging.Logger,
    level: int,
    message: str,
    stage: Optional[str] = None,
    latency_ms: Optional[float] = None,
    status: Optional[str] = None,
    **extra
):
    """
    Helper for emitting structured log records.
    
    Args:
        logger: The logger to use
        level: Logging level (logging.INFO, etc.)
        message: Log message
        stage: Pipeline stage (e.g., "retrieve", "rerank", "route")
        latency_ms: Operation latency in milliseconds
        status: Operation status ("success", "failed", "skipped")
        **extra: Additional fields to include
    """
    extra_dict = extra.copy()
    if stage:
        extra_dict['stage'] = stage
    if latency_ms is not None:
        extra_dict['latency_ms'] = latency_ms
    if status:
        extra_dict['status'] = status
    
    logger.log(level, message, extra=extra_dict)


# ==============================================================================
# SETUP FUNCTION
# ==============================================================================

def setup_logging(
    log_dir: Optional[Path] = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    json_logs: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> None:
    """
    Configure logging for the RAG system.
    
    Args:
        log_dir: Directory for log files (default: ./logs)
        console_level: Minimum level for console output
        file_level: Minimum level for file output
        json_logs: If True, file logs are JSON-structured
        max_bytes: Max size per log file before rotation
        backup_count: Number of rotated files to keep
    """
    # Default log directory
    if log_dir is None:
        from .config import get_config
        log_dir = get_config().paths.logs_dir
    
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Capture everything, filter at handlers
    
    # Remove existing handlers
    root.handlers.clear()
    
    # Console handler (human-readable)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(ReadableFormatter())
    root.addHandler(console)
    
    # Main log file (rotating)
    main_log = log_dir / "rag_v2.log"
    file_handler = logging.handlers.RotatingFileHandler(
        main_log,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(file_level)
    
    if json_logs:
        file_handler.setFormatter(StructuredFormatter())
    else:
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    root.addHandler(file_handler)
    
    # Error-only log (for quick debugging)
    error_log = log_dir / "rag_v2_errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(StructuredFormatter())
    root.addHandler(error_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
    logging.getLogger('transformers').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('qdrant_client').setLevel(logging.WARNING)
    
    logging.info("Logging initialized", extra={"stage": "startup", "log_dir": str(log_dir)})


# ==============================================================================
# QUERY TRACE LOGGER
# ==============================================================================

class QueryTraceLogger:
    """
    Specialized logger for query traces.
    Writes to query_trace.jsonl for analysis.
    """
    
    def __init__(self, log_dir: Path):
        self.trace_path = log_dir / "query_trace.jsonl"
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def log_trace(self, trace: Dict[str, Any]) -> None:
        """Append a query trace to the JSONL file."""
        # Add timestamp if not present
        if 'timestamp' not in trace:
            trace['timestamp'] = datetime.now().isoformat()
        
        with open(self.trace_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(trace, default=str) + '\n')
    
    def read_traces(self, limit: int = 100) -> list:
        """Read recent traces (newest first)."""
        if not self.trace_path.exists():
            return []
        
        traces = []
        with open(self.trace_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    traces.append(json.loads(line))
        
        return traces[-limit:][::-1]


# ==============================================================================
# CLI TEST
# ==============================================================================

if __name__ == "__main__":
    # Test logging setup
    setup_logging(log_dir=Path("./test_logs"))
    
    logger = logging.getLogger(__name__)
    
    # Test different log levels
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # Test structured logging
    log_structured(
        logger,
        logging.INFO,
        "Retrieval complete",
        stage="retrieve",
        latency_ms=45.2,
        status="success",
        chunk_count=10
    )
    
    # Test stage logger
    stage_logger = get_stage_logger(__name__, "rerank")
    stage_logger.info("Reranking started", extra={"latency_ms": 120.5})
    
    print("\n✓ Logging test complete. Check ./test_logs/")
