# Operator Run Profiles

This module provides an abstraction layer (Ops Layer) to safely trigger the frozen market intelligence pipeline.
It encapsulates complex orchestrator arguments into safe, predefined `OperatorProfile` enums, preventing malformed manual arguments and accidental network egresses.

## Profiles
- `dry_run_latest`: Reads newest parquets, computes everything, never sends out webhooks.
- `send_if_allowed_latest`: Full local loop, issues `--send` flag explicitly if the Policy Gate approves.
- `status_only`: Reads previously generated pipeline, policy, and parquet states without starting subprocesses.
- `debug_latest`: Standard dry run but outputs verbosely.
