# ACCEPTANCE: Market Report Pipeline Runner v0.3

**VERDICT: ACCEPTED**

## 1. Goal 
Allow the pipeline runner to explicitly load a real ingestion file path (`--snapshot-input PATH`) and cascade the data directly down to the snapshot builder when using `--input-mode generated`.

## 2. Changes Made
- **`pipelines/market_report_pipeline_runner/schemas.py`**: Expanded `PipelineResult` to natively record `snapshot_input_path`, `snapshot_source_type`, and `used_real_ingestion_input`.
- **`pipelines/market_report_pipeline_runner/cli.py`**: Added `--snapshot-input` argument logic.
- **`pipelines/market_report_pipeline_runner/runner.py`**: Subprocess routing upgraded to bridge `snapshot_input` directly into the `market_snapshot_builder` process as `--input PATH`.

## 3. Tests Executed
- **Unit Tests**: `test_market_report_pipeline_runner.py` ran correctly. Verified logic for path bridging and fallback static `--sample` logic.
- **System Run**: E2E Dry-run (`python -m pipelines.market_report_pipeline_runner.cli run --input-mode generated --snapshot-input "C:\CryptoSystems\Collector - OKX\data\normalized\okx\candles\source=okx_ws\symbol=BTC-USDT-SWAP\date=2026-04-25\hour=03\part-1777088176053.parquet" --dry-run`) passed safely. 
- **Boundaries**: Evaluated boundaries via `check_boundaries.py` (Passed).

## 4. Pipeline Results
- The latest `PipelineResult` successfully logged `used_real_ingestion_input: true` and the exact `.parquet` source path.
- The pipeline securely processed data via the existing state gate constraints (`DOWNGRADE_DRY_RUN_ONLY`), preventing accidental live egress.

## 5. Summary
The pipeline runner natively supports loading any specific parquet partition through the CLI wrapper. It seamlessly translates raw ingestion payload down to all producers and retains 100% frozen boundaries and isolated subprocess telemetry.
