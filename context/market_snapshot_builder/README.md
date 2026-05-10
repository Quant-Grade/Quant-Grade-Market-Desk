# Market Snapshot Builder v0.1

This module acts as the core translation bridge between upstream data ingestion feeds and the strict schemas demanded by the frozen analyst producers (VWAP, Session Open, Liquidity Bands). 

## Mission
To consume unstructured or broadly structured OHLCV blobs and selectively route their attributes into tightly bound JSON inputs for the analysts. This builder does NOT generate signals, prompt LLMs, or send webhooks. It simply builds context snapshots.

## Features
- Validates the incoming source payload strictly via `schemas.py` (`SourceOHLCVSnapshot`).
- Automatically computes missing scalar metrics (e.g., `distance_to_vwap`, `distance_to_zone_pct`).
- Validates every generated JSON against the downstream Producer's native schema parser before writing to disk.
- Fails closed if the source data is malformed or lacks necessary fields.

## Usage

For v0.1, we rely on local fixture logic:

```bash
python -m context.market_snapshot_builder.cli build --sample
```

This generates:
- `inputs/generated/latest_vwap_input.json`
- `inputs/generated/latest_session_open_input.json`
- `inputs/generated/latest_liquidity_bands_input.json`
- `outputs/context/latest_market_snapshot.json`
