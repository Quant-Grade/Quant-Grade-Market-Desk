# ACCEPTANCE: Operator Run Profiles v0.1

**VERDICT: ACCEPTED**

## 1. Goal
Build an abstracted `ops/operator_run_profiles` layer mapping rigid command combinations down to the pipeline, safeguarding deterministic execution and actively blocking malformed network egress sequences.

## 2. Changes Made
- `[NEW]` `ops/operator_run_profiles/__init__.py` & `README.md`
- `[NEW]` `ops/operator_run_profiles/schemas.py`: `OperatorProfile` enum encapsulating `dry_run_latest`, `send_if_allowed_latest`, `status_only`, and `debug_latest`.
- `[NEW]` `ops/operator_run_profiles/profiles.py`: Isolated validation matrix.
- `[NEW]` `ops/operator_run_profiles/runner.py`: Spawns lower-level `pipelines.market_report_pipeline_runner.cli` with explicit boundary-validated combinations depending on the selected profile. Decoupled `status_only` safely reads JSONs globally without launching processes.
- `[NEW]` `ops/operator_run_profiles/cli.py`: The user-facing operational hook tracking to `outputs/ops/latest_operator_run.json`.
- `[NEW]` `tests/test_operator_run_profiles.py`: Total verification that profiles spawn subprocess strings securely.

## 3. Tests Executed
- **Unit Tests**: Asserts correct sub-flags (`--send` vs `--dry-run`), correct pipeline invocation paths, and accurate `status_only` fail-safes. Passed.
- **Dry-Run CLI**: `python -m ops.operator_run_profiles.cli run --profile dry_run_latest --symbol BTC-USDT-SWAP`. Subprocesses cascaded cleanly. The orchestrator ran the parquet resolver, the snapshot builder, the analyst pack, the LLM, and successfully exited to a Blocked `DRY_RUN`.
- **Status Hook CLI**: `python -m ops.operator_run_profiles.cli status`. Returned the full structural state payload seamlessly.
- **Boundaries**: Re-ran `tools\check_boundaries.py` (Passed).

## 4. Final Output Verification
The pipeline is now accessible safely through a zero-ambiguity enum selection, drastically reducing the possibility of accidental pipeline contamination or unintended network broadcasts.
