# Market Report Pipeline Runner v0.1

This is the top-level orchestrator. It acts as the singular deterministic execution path for the entire intelligence loop.

## Mission
To sequentially fire analyst modules, aggregate their deterministic combinations, query the LLM generator, filter the output through the spam gate, and ultimately transmit to Discord via Egress. 

## Flow
1. VWAP Producer
2. Session Open Producer
3. Liquidity Bands Producer
4. Combiner
5. Local LLM Writer (Can be skipped via `--skip-llm`)
6. Alert Policy Gate
7. Discord Webhook Egress

## Safety
- Default behavior is `--dry-run` and WILL NOT trigger network POST messages to the Discord Webhook URL.
- To execute a live post, `--send` must be explicitly appended to the CLI run.
- Policy gates hold supreme authority. Even if `--send` is passed, if the Policy Gate returns `BLOCK_DUPLICATE` or `BLOCK_COOLDOWN`, the egress process will be aborted instantly.

## Usage
Run pipeline in safe dry-run mode:
```bash
python -m pipelines.market_report_pipeline_runner.cli run
```

Run pipeline in live broadcast mode:
```bash
python -m pipelines.market_report_pipeline_runner.cli run --send
```
