# REGRESSION_NET — combined gate coverage + smoke classification

**Status:** active. Paired with `tools/verify_all.py` (enforcement).
**Applies to:** RAG_SYSTEM only.
**Companion docs:** `BOUNDARIES.md` (import/write zones), `SCHEMAS.md` (envelope registry).

This document names every check that guards regression in this repository, states what each check covers, and classifies the current smoke-suite drift cluster-by-cluster so nothing is silently codified and nothing is silently lost.

`tools/verify_all.py` is the single entry point. A successful `verify_all` run is the gate for any code change landing in this repo.

---

## 1. Gate policy

Three status classes:

| Class | Meaning | Effect on `verify_all` exit code |
|---|---|---|
| **Gated** | Must pass for verify_all to exit 0. A failure is a real regression. | Any failure → exit 1. |
| **Advisory** | Reported but not gated. Used for checks that are currently drifted against src and awaiting classified alignment. | Failures do not affect exit code; reported as `advisory_failures=N`. |
| **Internal error** | The check itself could not run (missing file, Python broken, etc.). | Any occurrence → exit 2. Distinct from a real regression. |

A check graduates from advisory → gated only after its drift is classified, aligned, and reproducibly green.

---

## 2. Gated coverage (current)

Nine gates. Every one of them was green at the time this document landed. Do not weaken any of them without replacing the coverage.

### 2.1 P1 — atomic commit + rollback
- **Harness:** `tools/verify_p1_atomic_commit.py`
- **Covers:** `commit_round_checkpoint` writes `alpha_concepts.jsonl` line + `idea_log.md` block as an atomic pair; on any write exception, both files are truncated back to pre-call byte lengths via `_truncate_file_to_bytes`. Also covers byte-level rollback semantics via `Path.open` monkey-patch to force a mid-write failure.
- **Green markers:** `commit_ok`, `rollback_ok`.

### 2.2 Wave 1 — P6 + P2 + P3
- **Harness:** `tools/verify_wave1.py`
- **Covers:** P6 bounds gate (`_require_operational_limits_or_exit`), P2 resume from last checkpoint (`load_last_alpha_jsonl_record` + `rebuild_last_round_texts_from_jsonl`), P3 baton (Builder receives `PRIOR_STATE_TRACKER` and `PRIOR_ORGANIZED_MEMORY` from prior round).
- **Green markers:** `p6_missing_ok`, `p6_allow_ok`, `p2_ok`, `p3_ok`, `wave1_all_ok`.

### 2.3 Wave 2 — P5 + P8 (Round-85 contract)
- **Harness:** `tools/verify_wave2.py`
- **Covers:** P5 theory_log append-only (`prepend_state_summary` appends YAML-frontmatter blocks to `theory_log.md`; never touches `idea_log.md`; no `.tmp` scratch file; subsequent calls append rather than replace; empty summary is no-op). P8 alpha_concepts.jsonl rotation via `maybe_rotate_alpha_jsonl` when `ALPHA_JSONL_MAX_BYTES` / `ALPHA_JSONL_MAX_LINES` exceeded.
- **Green markers:** `p5_prepend_ok`, `p8_rotate_ok`, `p8_no_rotate_ok`, `wave2_all_ok`.
- **History note:** this harness was silently asserting the pre-Round-85 contract from Round 66 through Round 87. It was re-aligned to Round-85 in S0.5 and is now a truthful gate again.

### 2.4 Wave 3 — P4 + P7
- **Harness:** `tools/verify_wave3.py`
- **Covers:** P4 round-flow ordering (Builder → RAG → Compressor → RedTeam → Leader; all three mid-stage roles receive the same compacted rag_context; Leader gets the full idea_expansion). P7 strict-JSON Leader (default temperature=0, one repair pass on parse failure, explicit fail-state with `parse_error: true` when repair also fails, opt-in prose escape hatch via `ALPHA_ALLOW_PROSE_LEADER_BATON=1`, loose path when `ALPHA_STRICT_LEADER_JSON=0`).
- **Green markers:** `p4_order_ok`, `p7_strict_fail_ok`, `p7_strict_ok_ok`, `p7_prose_escape_ok`, `p7_loose_temp_ok`, `wave3_all_ok`.

### 2.5 Proof A — governance foundation
- **Harness:** `artifacts/verification/governance_foundation_proof_a.py`
- **Covers:** A-lite governance foundation — score_range, option_count, baton_mismatch_control (baton-sync-on-mismatch behavior), checkpoint envelope shape. Governance is OFF by default (`ALPHA_GOVERNANCE_OPTIONS` unset); this proof exercises the ON path end-to-end.
- **Green marker:** `PROOF_A_OK score_range option_count baton_mismatch_control checkpoint`.

### 2.7 `check_api_contract` — frozen-surface contract (`orchestrator.py`)
- **Harness:** `tools/check_api_contract.py`
- **Covers:** verifies that every symbol API_CONTRACT.md §3 freezes exists at module scope in `orchestrator.py`. Catches silent renames, removals, and moves-without-re-export that would invalidate the regression net. 17 symbols currently tracked (3 module attributes + 5 underscored-but-contractual private functions + 9 public functions).
- **Green marker:** `api_contract_ok <N>_symbols_verified`.

### 2.6 `check_boundaries` — zone import contract
- **Harness:** `tools/check_boundaries.py`
- **Covers:** three rules from BOUNDARIES.md §6.
  1. No file under `rag_system_v2/src/**` imports `orchestrator` (any form).
  2. `orchestrator.py` imports from `src.*` only via the three approved targets (`src.router`, `src.retrieve`, `src.query_alpha_memory`).
  3. No file under `rag_system_v2/src/**` imports root-level one-off scripts (`inspect_alpha_concepts`, `inspect_state_tracker`, `smoke_alpha_round`).
- AST-based (not string-grep); Zone D files (`.pre_hardening`, `.bak_*`, `.md.tmp`, `SMG-OS.txt`, cache dirs) are excluded.
- **Green marker:** `boundaries_ok`.

### 2.7 Doctor — rag_system_v2 health
- **Harness:** `python -m src.doctor` (cwd `rag_system_v2/`)
- **Covers:** all 5 required files present; `manifest.json` schema valid (currently v3) and internally consistent; `chunks.jsonl` validity (2296 / 2296 with correct field names — see SCHEMAS.md §2.6); BM25 index load via `BM25Index.load` classmethod + `get_stats()`; parents.sqlite row count; Qdrant vector count + dimension; ID consistency across BM25 + Qdrant + chunks; single-query latency; LM Studio reachability (INFO-level check, does not affect HEALTHY status on network failure).
- **Green marker:** `OVERALL: [+] HEALTHY` with Pass/Warn/Fail counts.

### 2.8 Smoke suite — rag_system_v2 foundation invariants
- **Harness:** `python -m pytest rag_system_v2/tests/test_smoke.py -q` (cwd repo root)
- **Covers:** chunk-id determinism, SHA-256 stability, BM25 tokenization, router enum surface, citation verifier fail-closed, router threshold ordering + paths, manifest `SCHEMA_VERSION`, embedding dimension consistency, **injection patterns** (via `InjectionDetector` + `RouterConfig.injection_patterns`), RRF merge tuple return.
- **Green marker:** `10 passed` (pytest quiet).
- **History:** S4b aligned test-side drift; injection bar closed by extending `injection_patterns` in `rag_system_v2/src/config.py` (not by weakening the smoke assertion). Smoke migrated from advisory → gated in the same pass.

---

## 3. Envelope-lint policy (prospective)

Not yet wired into `verify_all.py`; documented here as a binding rule for any future lint addition.

Per SCHEMAS.md §3, the four reader-tolerance outcomes are:
- **`schema_version_missing_legacy_accept`** — legitimate on pre-envelope historical data.
- **`schema_version_missing_expected`** → fail-closed reason code `missing_schema_version`.
- **`schema_version_unknown`** → fail-closed reason code `unknown_schema_version`.
- **`schema_version_type_drift`** → fail-closed reason code `schema_version_type_drift`.

When envelope-lint is added to `verify_all.py`:

**The lint policy must mirror the reader-tolerance rule exactly.** It is an error if lint is stricter than readers (legitimate legacy records appear broken) or more lenient than readers (lint passes data that runtime will reject).

Concretely:
- For each versioned artifact listed in SCHEMAS.md §2, identify the `first_envelope_ts` — the earliest timestamp at which the writer emitted the envelope. Records with `ts < first_envelope_ts` AND missing version are legacy (accepted). Records with `ts >= first_envelope_ts` AND missing version are missing_expected (failed).
- Unknown version values (present but not in the supported set) always fail.
- Type-drift on the version token (e.g., `"v": "1"` instead of `"v": 1`) always fails.
- The lint rule set is version-pinned: when a new envelope version is added to SCHEMAS.md §2, the lint rule for that artifact is updated in the same PR.

---

## 4. Smoke-suite classification (S4a)

**Current:** smoke is **gated** in `verify_all.py` and **10/10 green** after S4b (tests) plus the injection-pattern extension in `RouterConfig.injection_patterns` (`config.py`). The subsections below retain the **historical S4a/S4b classification table** for audit traceability; do not read them as today's pass/fail state.

### 4.1 Classification table

Conventions used:
- **TEST DRIFTED** — test encodes an old API; current `src` design is deliberate and more disciplined.
- **INVOCATION DRIFT** — test imports modules as top-level scripts; modules use package-relative imports (`from .config`) that need package context.
- **STALE ASSERT** — test asserts an expected value that has since changed legitimately.

| # | Test | Passes today | Classification | Evidence |
|---|---|---|---|---|
| 1 | `test_hash_consistency` | ✓ | (green) | SHA-256 stability test; unaffected by drift. |
| 2 | `test_bm25_tokenization_stability` | ✓ | (green) | `BM25Tokenizer` interface stable. |
| 3 | `test_chunk_id_determinism` | ✗ | **TEST DRIFTED** | Test asserts `':' in id1 or '_' in id1`. Current `compute_stable_chunk_id` returns a 12-char lowercase hex hash (e.g., `'411d64326607'`). Separators live in `RetrievedChunk.citation_id()` (`{doc_prefix}:{page}:{chunk_hash[:4]}`). **The separation of content-addressed chunk_id (raw hash) from structured citation_id (human-readable) is intentional and more disciplined than what the test asserts.** |
| 4 | `test_router_decision_mapping` | ✗ | **TEST DRIFTED** | Test expects `ModelTier.FAST.value == 'FAST'` (uppercase). Current src defines `ModelTier.FAST = "fast"` (lowercase) deliberately to match LM Studio model aliases (`LLMConfig.fast_model = "fast"` default). `RouterDecision` values stay uppercase (protocol-level); `ModelTier` values are lowercase (model-alias-level). Inconsistency is by design. |
| 5 | `test_verify_fail_closed` | ✗ | **INVOCATION DRIFT** | `ImportError: attempted relative import with no known parent package` at `verify.py:34 (from .config import …)`. Test does `sys.path.insert(0, str(_RAG_V2_ROOT / "src"))` then `from verify import CitationVerifier`, which imports `verify` as a top-level module and breaks its `from .config` relative import. Same root cause as #7 and #9. |
| 6 | `test_config_validation` | ✗ | **TEST DRIFTED** | Test reads `config.router.refuse_threshold / clarify_confidence / retrieve_confidence / direct_confidence` (unprefixed). Current `RouterConfig` uses `t_refuse_threshold / t_clarify_confidence / t_retrieve_confidence / t_direct_confidence` — a uniform `t_` prefix across all thresholds. The `t_` prefix is more disciplined (distinguishes thresholds from scores). |
| 7 | `test_manifest_schema_version` | ✗ | **INVOCATION DRIFT + STALE ASSERT** | Two independent issues: (a) `ImportError` via `from build_all import SCHEMA_VERSION, Manifest` (same root cause as #5, #9); (b) `assert SCHEMA_VERSION == 2` is now stale — S2 bumped the constant to `3`. Both need fixing. |
| 8 | `test_embedding_config_consistency` | ✗ | **TEST DRIFTED** | Test reads `config.embedding.model_name` and `config.embedding.dimension`. Current `EmbeddingConfig` uses `model` (not `model_name`) and `dimensions` (not `dimension`). |
| 9 | `test_injection_detection_exists` | ✗ | **INVOCATION DRIFT + PRODUCT GAP** | Invocation drift (relative-import) was one of two failures. S4b's alignment fixed the import; the test then revealed a second, previously-masked failure: current `InjectionDetector` patterns miss 3 of 4 canonical injection strings. See §4.4 for escalation. |
| 10 | `test_rrf_merge_correctness` | ✗ | **TEST DRIFTED** | Test calls `merger.merge(vector_results, bm25_results)` with 2 args and uses `merged[0].chunk_id`. Current `merger.merge(v, b, top_k=...)` requires `top_k` kwarg and returns a tuple `(merged_list, merge_stats)`. The tuple return is proven by `retrieve.py:298` which destructures as `merged, merge_stats = merger.merge(...)`. The test's 2-arg call hits a default path (if `top_k` is optional) but the return is a tuple, so `merged[0]` is a list and `.chunk_id` on a list fails. |

### 4.2 Clustering for S4b alignment (deferred, not executed)

| Cluster | Members | Alignment |
|---|---|---|
| **INVOCATION DRIFT** (one fix covers three) | #5, #7, #9 | Change the test's `sys.path.insert(0, str(_RAG_V2_ROOT / "src"))` to `sys.path.insert(0, str(_RAG_V2_ROOT))` AND rewrite imports as `from src.verify import …` / `from src.build_all import …` / `from src.router import …`. This makes imports package-scoped and resolves `from .config` correctly. |
| **Attribute rename drift** | #4, #6 | Update test to use current names: `ModelTier.FAST.value == "fast"`; `config.embedding.model` and `config.embedding.dimensions`. |
| **Threshold prefix drift** | #6 (config_validation, the threshold-ordering part) | Update test to use `t_refuse_threshold / t_clarify_confidence / t_retrieve_confidence / t_direct_confidence`. |
| **Stale schema version assertion** | #7 | Update `assert SCHEMA_VERSION == 2` → `assert SCHEMA_VERSION == 3`. (Or, better, simply `assert SCHEMA_VERSION >= 1` since that is what actually matters.) |
| **Chunk-id contract drift** | #3 | Replace separator assertion with something that matches the current contract: e.g., `assert len(id1) == 12 and all(c in '0123456789abcdef' for c in id1)`. |
| **RRF return shape drift** | #10 | Rewrite the assertion as `merged_list, stats = merger.merge(vector_results, bm25_results, top_k=10)` then `merged_list[0].chunk_id == "B"`. |

### 4.4 Post-S4b status + injection resolution

**Resolved (operator-approved src fix):** `RouterConfig.injection_patterns` gained five regexes so `InjectionDetector` matches the four smoke canonical strings while keeping detection config-driven (compiled in `router.InjectionDetector`). Patterns added:
- `r"ignore\s+(?:all\s+)?(?:previous|above)\s+instructions"` — bridges "ignore all previous instructions …" vs the older single-token `ignore (previous|above|all) instructions`.
- `r"disregard\s+safety\s+guidelines"` — covers the smoke `[[OVERRIDE]] …` line’s tail without broadening `disregard` to arbitrary objects.
- `r"(?m)^\s*system\s*:"` — line-initial `SYSTEM:` role injection (complements substring `you are now`).
- `r"```\s*\n?\s*you\s+must\s+now\s+follow"` — fenced block + imperative stack from smoke.
- `r"\[\[\s*override\s*\]\]"` — banner token (case-insensitive at compile time).

**Smoke status:** 10/10 pass; smoke check moved from `ADVISORY` to `GATED` in `tools/verify_all.py`.

### 4.3 What S4b must NOT do

- **S4b discipline was tests-only.** The historical rule was: do not patch `rag_system_v2/src/**` to silence smoke during S4b. The later **injection_patterns** change in `config.py` was a separate, operator-approved **src** fix after drift classification proved a real detector gap (§4.4).
- **Do not lower any assertion to "pass on today's output".** Each alignment must encode the current contract's intent (e.g., content-addressed chunk_id, `t_`-prefixed thresholds, tuple-returning merge) as a forward-looking regression net, not a "matches current output" tautology.
- **Do not gate on smoke until EVERY failing test is aligned and reproducibly green.** Partial-green smoke in `verify_all.py` creates a false comfort zone.

---

## 5. Deliberately excluded from this regression net

Documented so that their absence is explicit, not accidental:

- **Bounded live round** (full orchestrator loop against LM Studio). The alpha loop's live invocation is a production run that mutates state and depends on an external LM endpoint; including it in `verify_all.py` would couple the gate to LM Studio uptime. Live runs are operator-triggered, not CI-gated.
- **Gate 2 captured-trace re-execution.** The 11 `gate2_round*.txt` captures are classified in `artifacts/verification/gate2_capture_classification.md`; re-executing them would require LM Studio plus a seed-deterministic replay harness. Out of scope for S4.
- **Multi-line resume window proof** (`ALPHA_RESUME_REBUILD_WINDOW > 1`). Currently only `window=1` is covered by P2; multi-line is a blind-spot deferred per the S0 baseline. When a harness for it is written, it joins Wave 1.
- **Scribe hash-chain replay against full history** (oracle-style verification of every alpha_concepts line against its scribe entry). Deferred to Scribe v1 (chained `prev_hash`) design, which is post-current-roadmap.

---

## 6. Change discipline for this document

- A new harness added to `verify_all.py` adds a row under §2 in the same PR.
- A smoke drift cluster aligned in S4b removes itself from §4.1 and, on green reproducibility, migrates from `ADVISORY` to `GATED` in `tools/verify_all.py` — the SCHEMAS.md-style "document + enforcement ship together" discipline applies here too.
- If an advisory check is abandoned (e.g., smoke is rewritten as a different harness), its removal from `ADVISORY` is paired with a note in §5 describing why.
- Envelope-lint rules added to `verify_all.py` update §3 in the same PR.

---

## 7. Current-state attestation

At the time of this document's landing:

```
verify_all_ok  advisory_failures=0

  [+] P1 atomic commit
  [+] Wave 1 (P6 + P2 + P3)
  [+] Wave 2 (P5 + P8)
  [+] Wave 3 (P4 + P7)
  [+] Proof A (governance)
  [+] check_boundaries
  [+] check_api_contract
  [+] doctor  (HEALTHY 10/10, manifest v3)
  [+] smoke suite  (10 passed; injection patterns aligned per §4.4)
```

Exit code: **0** (all gated checks green; no advisory harnesses configured).

No gate is provisionally green. Every gated check in §2 has been re-run against the current tree and reports its green marker exactly as documented.
