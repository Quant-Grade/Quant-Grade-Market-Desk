import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from .schemas import ParquetResolution, ResolverError
from context.market_snapshot_builder.ingestion_loader import load_real_ingestion_snapshot
from context.market_snapshot_builder.schemas import BuilderValidationError

def _parse_path_partitions(filepath: Path) -> Dict[str, str]:
    """Extract source=..., symbol=..., date=..., hour=... from path parts"""
    parts = filepath.parts
    extracted = {}
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            extracted[k] = v
    return extracted

def _get_sort_key(file_info: Dict[str, Any]) -> tuple:
    """Sort key for prioritizing candidates."""
    # We want descending order, so we negate/invert keys or sort reverse=True
    date = file_info["partitions"].get("date", "1970-01-01")
    hour = file_info["partitions"].get("hour", "00")
    mtime = file_info["mtime"]
    return (date, hour, mtime)

def resolve_latest_parquet(root_dir: str, symbol_filter: Optional[str] = None, source_filter: Optional[str] = None) -> ParquetResolution:
    root_path = Path(root_dir)
    if not root_path.exists() or not root_path.is_dir():
        raise ResolverError(f"Root directory does not exist or is not a directory: {root_dir}")

    # Gather all parquet files
    all_parquets = list(root_path.rglob("*.parquet"))
    if not all_parquets:
        raise ResolverError(f"No .parquet files found under {root_dir}")

    candidates = []
    for p in all_parquets:
        partitions = _parse_path_partitions(p)
        
        # Apply filters
        if symbol_filter and partitions.get("symbol") != symbol_filter:
            continue
        if source_filter and partitions.get("source") != source_filter:
            continue
            
        candidates.append({
            "path": p,
            "partitions": partitions,
            "mtime": p.stat().st_mtime
        })

    if not candidates:
        raise ResolverError("No .parquet files matched the given filters.")

    # Sort descending
    candidates.sort(key=_get_sort_key, reverse=True)

    # Validate sequentially
    for candidate in candidates:
        candidate_path = str(candidate["path"])
        
        try:
            # Try loading it through the frozen ingestion loader
            load_real_ingestion_snapshot(candidate_path)
            
            # If it succeeds, this is our winner
            return ParquetResolution(
                resolved_path=candidate_path,
                source=candidate["partitions"].get("source"),
                symbol=candidate["partitions"].get("symbol"),
                date=candidate["partitions"].get("date"),
                hour=candidate["partitions"].get("hour"),
                timestamp_found=datetime.now(timezone.utc).isoformat()
            )
        except BuilderValidationError:
            # File is malformed or missing OHLCV, try the next one
            continue
        except Exception:
            # Broad catch for unexpected pandas errors
            continue
            
    raise ResolverError("No valid .parquet files could be successfully parsed and validated.")
