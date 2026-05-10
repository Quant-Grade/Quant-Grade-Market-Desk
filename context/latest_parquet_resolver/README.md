# Latest Parquet Resolver

A deterministic module designed to recursively scan a target directory tree (typically OKX ingestion outputs) for the most recent `.parquet` payload.

This module acts as a "Finder" to bridge autonomous pipelines with dynamically generated market partitions without requiring an active database connection.

### Core Behaviors:
- **Scan & Extract:** Recursively crawls `.parquet` files and extracts schema tags (`source=...`, `symbol=...`, `date=YYYY-MM-DD`, `hour=HH`) from the path.
- **Strict Sorting:** Sorts candidates descending by chronological folder tags first, then by OS file modification time.
- **Fail-Closed Validation:** Submits candidates to `context.market_snapshot_builder.ingestion_loader` to ensure the parquet is fully readable, structurally intact, and contains all necessary OHLCV boundaries. The first to pass is emitted.
