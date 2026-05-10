# API_CONTRACT — `orchestrator.py` frozen-surface registry

**Status:** active contract, enforced by `tools/check_api_contract.py`.
**Version:** 1.
**Applies to:** RAG_SYSTEM repo root `orchestrator.py` only.
**Companion docs:** `BOUNDARIES.md` (zones), `SCHEMAS.md` (envelopes), `REGRESSION_NET.md` (combined gate).

This document freezes every symbol in `orchestrator.py` that the regression net depends on. The five wave/proof harnesses (`tools/verify_p1_atomic_commit.py`, `verify_wave1.py`, `verify_wave2.py`, `verify_wave3.py`, `artifacts/verification/governance_foundation_proof_a.py`) import `orchestrator` and reach into specific attributes and functions — including several with leading underscores that would otherwise look private. **Despite the underscores, these symbols are part of a public contract**: renaming or moving them without coordinated harness updates breaks the regression net in a way that is invisible until the next harness run.

`tools/check_api_contract.py` is the enforcement companion. It imports `orchestrator` and verifies every symbol listed in §3 exists at module scope. On violation, exit non-zero with a named reason code. Run as part of `tools/verify_all.py` at the next S4 evolution (not yet wired; see §5).

---

## 1. Why this contract exists

Prior audits identified root cause α (code locality / harness coupling): `orchestrator.py` is a 1,880-line file, and the regression net that proves its invariants reaches into private symbols by name. Any α-level work (role-module split, persistence extraction, etc.) that renames or moves these symbols without same-PR harness updates will silently invalidate the regression net.

Freezing the surface here does **not** prevent refactoring. It makes refactoring explicit: if a future PR needs to rename or move a listed symbol, the PR must also update this document, the grep companion, and every harness that imports the symbol. The contract is the coordination mechanism.

---

## 2. Scope and non-scope

**In scope (this document governs):**
- Symbols at module scope (top-level assignments and `def`/`class` declarations) in `orchestrator.py`.
- Symbols that are imported by name or attribute-accessed by any of the five harnesses listed above.

**Out of scope (this document does NOT govern):**
- Internal helpers that happen to live inside the functions listed here (e.g., closures inside `commit_round_checkpoint`). They can change freely without a contract update.
- Symbols used only by `main()` or by orchestrator-internal call paths that no harness reaches.
- Environment variables consumed by orchestrator (`ALPHA_*` env names); those are a separate operator contract outside this document.
- Schema versions (`ALPHA_CHECKPOINT_V`, `IDEA_LOG_ROUND_SECTION_V`, `SCRIBE_EVENT_V`) — already governed by `SCHEMAS.md`.

---

## 3. Frozen symbols (empirically enumerated, not aspirational)

Enumerated by grepping every `o.<name>`, `orchestrator.<name>`, and `x.<name>` attribute access in the regression-net harness source at the time of this document's landing. Every entry names the symbol, what it is, and which harness depends on it.

### 3.1 Module-level attributes (monkey-patchable)

These are module-level bindings that harnesses reassign to redirect writes into tempdirs. Renaming any of them breaks the harness's ability to isolate its test from production data.

| Symbol | Kind | Harnesses |
|---|---|---|
| `_rag_v2_base` | `Path` binding set at import time from `Path(__file__).resolve().parent / "rag_system_v2"` | `verify_p1_atomic_commit.py` |
| `IDEA_LOG_PATH` | `Path` binding for `idea_log.md` at repo root | `verify_p1_atomic_commit.py`, `verify_wave2.py` |
| `THEORY_LOG_PATH` | `Path` binding for `theory_log.md` at repo root | `verify_wave2.py` |

### 3.2 Private functions (underscored, frozen despite leading `_`)

These are called directly by harnesses to exercise specific invariants without triggering a full `main()` loop. The leading underscore is historical; from the regression net's perspective they are public contract.

| Symbol | Harness | Invariant asserted |
|---|---|---|
| `_require_operational_limits_or_exit` | `verify_wave1.py` | P6: unbounded loop is opt-in; missing `ALPHA_MAX_ROUNDS`/`ALPHA_MAX_WALL_SEC` → `sys.exit(2)` before LM client setup. |
| `_leader_governance_diagnose` | `governance_foundation_proof_a.py` | Returns first failing A-lite clause code on a governance-options Leader payload. |
| `_try_governance_baton_sync_if_only_mismatch` | `governance_foundation_proof_a.py` | Sync baton_pass.next_task to selected_option.next_task iff baton_mismatch is the only failing clause. |
| `_debug_governance_log_clause` | `governance_foundation_proof_a.py` | Opt-in log emission for first failing clause when `ALPHA_DEBUG_GOV=1`. |
| `_leader_governance_fail_state` | `governance_foundation_proof_a.py` | Canonical fail-closed state dict for governance validation failure. |

### 3.3 Public functions (no underscore, unambiguously contract)

| Symbol | Harness | Purpose |
|---|---|---|
| `commit_round_checkpoint` | `verify_p1_atomic_commit.py` | P1 atomic commit: alpha_concepts.jsonl line + idea_log.md block as an atomic pair with byte-level rollback. |
| `load_last_alpha_jsonl_record` | `verify_wave1.py` | P2 resume: last-line reader with schema-version tolerance (`_alpha_record_version_supported`). |
| `rebuild_last_round_texts_from_jsonl` | `verify_wave1.py` | P2 resume-window rebuild of `last_round_texts` from jsonl tail. |
| `call_builder` | `verify_wave1.py` (P3) | Builder role call; receives `prior_state_json` + `prior_organized_memory` for P3 baton. |
| `call_leader` | `verify_wave3.py` | Leader role call; strict-JSON default (P7) with one repair pass and explicit fail-state. |
| `prepend_state_summary` | `verify_wave2.py` | P5 Round-85 contract: append-only YAML-frontmatter block to `theory_log.md`; never rewrites `idea_log.md`. |
| `maybe_rotate_alpha_jsonl` | `verify_wave2.py` | P8 retention: rotate `alpha_concepts.jsonl` to `archive/` when `ALPHA_JSONL_MAX_BYTES` / `ALPHA_JSONL_MAX_LINES` exceeded. |
| `build_alpha_checkpoint_record` | `governance_foundation_proof_a.py` | Returns the versioned record dict (`"v": 1` first key per SCHEMAS.md §2.3) that `commit_round_checkpoint` serializes. |
| `main` | `verify_wave3.py` (reads via `inspect.getsource(o.main)`) | The loop body. Wave 3's P4 test inspects the source string to assert role-call ordering textually. |

**Total: 17 symbols.** Three module-level attributes, five underscored functions, nine public functions. If `check_api_contract.py` reports any other count on a fresh inventory, this document is out of date; the count and the document must be updated in the same PR.

---

## 4. Change discipline

### 4.1 Adding a new symbol to this contract
- A new symbol is added to §3 only when it is already consumed by a harness in the regression net. Speculative additions are rejected.
- The PR that adds the symbol also adds it to `tools/check_api_contract.py`'s `REQUIRED_SYMBOLS` tuple.

### 4.2 Renaming a listed symbol
- Introduce the new name in the same PR that adds the old name to `LEGACY_ALIASES` (new section of `check_api_contract.py`, where keys are the legacy names and values are the module attribute on which they should exist as an alias).
- Each harness that uses the symbol is updated to the new name in the same PR.
- A follow-up PR removes the legacy alias and the `LEGACY_ALIASES` entry.
- This is the **only** supported rename path.

### 4.3 Moving a listed symbol out of `orchestrator.py`
- The symbol must be re-exported from `orchestrator.py` so that `o.<name>` still works from harnesses.
- Example: if `call_builder` moves to `roles/builder.py`, `orchestrator.py` must contain `from .roles.builder import call_builder` at module scope, and `check_api_contract.py` must still find `o.call_builder` at module scope.
- Re-export is the contract mechanism that decouples internal structure from the harness interface.

### 4.4 Deprecating a listed symbol
- A deprecation deletes the symbol from §3 only when every harness that depends on it has been rewritten to not use it, and every rewrite has landed.
- The PR that deletes from §3 also deletes from `check_api_contract.py`.
- Deprecation is the reverse of §4.1.

### 4.5 Anti-patterns explicitly forbidden
- **Silent rename** (change symbol name without updating this document or harnesses). Breaks regression net invisibly.
- **Silent removal** (delete a symbol without updating §3 or its consumers). Same failure mode.
- **Partial rename** (update half the harnesses but not all). Produces per-harness false-green.
- **Underscore-is-private fallacy** ("`_leader_governance_diagnose` is private, I can rename it freely"). The contract makes it explicit that underscored names in §3.2 are frozen.

---

## 5. Enforcement

`tools/check_api_contract.py` imports `orchestrator` and verifies every symbol in §3 exists at module scope. On violation, it emits a named reason code (`api_contract_missing_symbol` with the offending name) and exits non-zero.

Wire it into `tools/verify_all.py` when the next S4-layer gate is added. Until then, run standalone:

```text
python -X utf8 tools/check_api_contract.py
```

Expected green output: `api_contract_ok <N>_symbols_verified`.

---

## 6. Current-state attestation

At the time of this document's landing:
- 17 symbols listed in §3 (3 attributes + 5 private functions + 9 public functions).
- `tools/check_api_contract.py` returns `api_contract_ok 17_symbols_verified` against the current `orchestrator.py`.
- No legacy aliases defined. When the first rename happens, §4.2 applies and the `LEGACY_ALIASES` section activates.
