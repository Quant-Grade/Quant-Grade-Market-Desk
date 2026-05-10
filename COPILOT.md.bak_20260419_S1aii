Alpha Engine COPILOT – Context Guardrails (Round 29)

- **Machine path registry:** `CANONICAL_PATHS.json` (repo root) — canonical pointers for orchestrator, RAG root, checkpoints, verification globs; use before inventing paths.
- You are worker-only, not the leader. Stay within the CURRENT TASK and `MASTER_PLAN.md`.
- Use repo evidence only (file reads/search); no guessing about missing pieces.
- Treat `rag_system_v2` as canonical RAG; only use retrieval/index paths present in `src/router.py`, `src/retrieve.py`, `src/index_qdrant.py`, `src/config.py`.
- Prefer minimal, local diffs to `orchestrator.py`; do not alter RAG internals.
- Live loop order: **Builder → RAG (`get_rag_context` + compact) → Compressor → RedTeam → Leader**; each committed round updates `rag_system_v2/data/alpha_concepts.jsonl` and `idea_log.md` via **`commit_round_checkpoint`** (atomic). See **Orchestrator runtime (current)** below.
- Always read `MASTER_PLAN.md` at the start of a round before inspecting or editing code.

## Orchestrator runtime (current)

*Canonical contract — aligned with `MASTER_PLAN.md` § Orchestrator runtime and `orchestrator.py`.*

### Per-round pipeline

1. **Builder** — `idea_expansion`, `query_memory_for`.
2. **RAG** — `rag_context = _compact_leader_rag_context(get_rag_context(query_memory))`; **same** `rag_context` for Compressor, RedTeam, and Leader.
3. **Compressor** — compacted Builder expansion + `rag_context`.
4. **RedTeam** — same `rag_context`, compacted expansion, plus **Compressor summary** in the user prompt.
5. **Leader** — **full** `idea_expansion` + `rag_context`.

### Operational limits (P6)

`ALPHA_ALLOW_UNBOUNDED_LOOP=1` **or** positive **`ALPHA_MAX_ROUNDS`** **or** **`ALPHA_MAX_WALL_SEC`**; else **exit 2** before LM client.

### Resume (P2)

`ALPHA_RESUME=1` → last jsonl line → `task` / `round_num` / `last_round_texts` rebuild (`ALPHA_RESUME_REBUILD_WINDOW`, default **5**). Empty jsonl + resume → **exit 3**.

### Baton (P3)

After commit, next Builder may receive **`PRIOR_STATE_TRACKER`** / **`PRIOR_ORGANIZED_MEMORY`**.

### Persistence (P1)

**`commit_round_checkpoint`** — jsonl + `idea_log` advance together; no round advance on partial failure.

### Prepend (P5)

**`idea_log.md.tmp`** → **`os.replace`** → `idea_log.md`.

### Retention (P8)

**`ALPHA_JSONL_MAX_BYTES`** / **`ALPHA_JSONL_MAX_LINES`** → rotate to **`rag_system_v2/data/archive/alpha_concepts_<UTC>.jsonl`**.

### Leader JSON (P7)

Default **`ALPHA_STRICT_LEADER_JSON=1`** (strict, `temperature=0`, repair pass). Failure path: **`leader_json_parse_failed`** + **`parse_error`** unless **`ALPHA_ALLOW_PROSE_LEADER_BATON=1`**. **`ALPHA_STRICT_LEADER_JSON=0`** → loose path (`temperature=0.2`).

Round 13: MASTER_PLAN.md read before edits. Env-gated Alpha self-memory append added: when `ALPHA_USE_SELF_MEMORY=1`, `get_rag_context` appends an "[Alpha self-memory]" block from isolated `bm25_alpha_index.pkl` + `data/qdrant_alpha` (collection `alpha_engine_children`) via `query_alpha_memory.get_alpha_self_memory_context`. Default behavior unchanged when flag unset. No changes to `retrieve.py`, router, or live/default indices.

Round 14: MASTER_PLAN.md read before execution. Bounded live run with ALPHA_MAX_ROUNDS=1 and ALPHA_USE_SELF_MEMORY=1 to prove Alpha self-memory append in real loop and alpha_concepts.jsonl write. Zero code changes unless execution proves a narrow bug.

Round 15: MASTER_PLAN.md read before edits. Orchestrator console/output hardened for Windows (log() prints console-safe string via _safe_console) so charmap on \u2192 etc. no longer crashes loop; file writes remain UTF-8. Rerun bounded self-memory proof.

Round 16: MASTER_PLAN.md read before execution. LM Studio diagnostic: /v1/models probe, minimal chat probe, bounded orchestrator rerun under same base/model/auth assumptions; identify first concrete blocker; no code change unless repo-side model/env mismatch proven.

Round 17: MASTER_PLAN.md read before edits. call_builder instrumented with minimal empty/invalid-output diagnostic (raw_len, preview, parsed_obj, keys); bounded rerun to prove next blocker.

Round 18: MASTER_PLAN.md read before edits. One strict Builder retry when parsed JSON has correct keys but both idea_expansion and query_memory_for empty; retry uses stricter prompt (min 1 sentence, min 2–6 word query); bounded rerun.

Round 19: MASTER_PLAN.md read before work. Restore default BM25 artifact (data/bm25_index.pkl) from existing repo-local chunks; bounded rerun to clear main RAG BM25 error while keeping Alpha self-memory append. No retrieval/router/orchestrator logic changes.

Round 20: MASTER_PLAN.md read before work. Align default chunks.jsonl from alpha_concepts_chunks.jsonl (artifact-only) to clear live "Chunks JSONL not found" warning; bounded rerun. No retrieval/router/orchestrator logic changes.

Round 21: MASTER_PLAN.md read before edits. One narrow Leader context-budget compaction in orchestrator (preserve [Alpha self-memory], trim to safe budget) before call_leader; bounded rerun to eliminate Leader 400 context overflow.

Round 22: MASTER_PLAN.md read before edits. Narrow role-input compaction for Compressor and RedTeam (preserve start of Builder expansion, truncate with marker); applied only at their call sites; bounded rerun to eliminate RedTeam 400 context overflow.

Round 23: MASTER_PLAN.md read before edits. Disable ANSI color codes when ALPHA_NO_COLOR=1 or stdout not a TTY so PowerShell logs are readable; bounded rerun. Logging-only; no loop/RAG/Alpha logic changes.

Round 24: Diagnosis-only. No code changes. Reproduce live multi-round run; identify first blocker from runtime evidence and repo code path. Do not fix, optimize, or anchor on one cause; let evidence lead. Report last successful step, first blocking point, and minimal code governing that transition.

Round 25: Diagnosis-only. Longer bounded run (same path: ALPHA_NO_COLOR=1, ALPHA_MAX_ROUNDS=3, ALPHA_USE_SELF_MEMORY=1) to distinguish slow progress from true stall; do not stop at 5 min if logs suggest normal progress. Capture last successful log line, next expected step, and whether process still progressing or stopped. Inspect only minimal code around that transition; no patches.

Round 26: Per-round organizer. One narrow organizer stage in orchestrator only: input = current round outputs (current_task, idea_expansion, compressor_output, redteam_output, next_task, state_tracker_json); output = compact sectioned deduplicated text via same LM/client. Persist: ### Organized memory in idea_log.md and organized_memory field in alpha_concepts.jsonl. No new roles, no baton/retrieval/index changes.

Round 27: Execution proof for non-empty organized memory. One bounded live round (ALPHA_MAX_ROUNDS=1, ALPHA_USE_SELF_MEMORY=1, ALPHA_NO_COLOR=1) with LM Studio up; verify compile_organized_memory returns non-empty and is persisted in idea_log.md and alpha_concepts.jsonl. Record pre/post line counts and tail proof. No code changes unless narrow organizer-specific runtime bug proven.

Round 28: Repeat execution proof for non-empty organized memory. Same bounded run (ALPHA_MAX_ROUNDS=1, ALPHA_USE_SELF_MEMORY=1, ALPHA_NO_COLOR=1, same test concept); pre/post jsonl line count and idea_log tail; prove organizer persistence in both formats or document blocker. No code changes unless organizer-specific bug proven.

Round 29: Deterministic fallback organizer. When compile_organized_memory fails or returns empty, use a narrow fallback helper (same section order: CONCEPT|EXPANSION|COMPRESSED|RISKS|NEXT|STATE) from current round values only; persist through existing path. No baton/retrieval/role changes. Verify non-empty organized_memory in both idea_log and jsonl when LM fails.

**Orchestrator Wave 1 (P2+P3+P6) — required env**
- **P6:** Either `ALPHA_ALLOW_UNBOUNDED_LOOP=1`, or at least one of `ALPHA_MAX_ROUNDS` / `ALPHA_MAX_WALL_SEC` must be a **positive** integer. Otherwise `orchestrator` exits **2** before any LM client is created.
- **P2 resume:** `ALPHA_RESUME=1` loads the last line of `rag_system_v2/data/alpha_concepts.jsonl`, sets `task` to `leader_next_task`, `round_num = last.round_id + 1`, rebuilds `last_round_texts` from tail (window `ALPHA_RESUME_REBUILD_WINDOW`, default **5**). Empty jsonl with resume → exit **3**.
- **P3:** After each committed round, the next Builder call receives `PRIOR_STATE_TRACKER` and optional `PRIOR_ORGANIZED_MEMORY` from the prior round.

**Orchestrator Wave 2 (P5+P8)**
- **P5:** `prepend_state_summary` rewrites `idea_log.md` via **`idea_log.md.tmp`** then **`os.replace`** (same directory as the log).
- **P8:** Optional positive **`ALPHA_JSONL_MAX_BYTES`** and/or **`ALPHA_JSONL_MAX_LINES`**. If the active `alpha_concepts.jsonl` exceeds either threshold, it is moved to **`rag_system_v2/data/archive/alpha_concepts_<UTC>.jsonl`** (`os.replace`); the next commit starts a fresh jsonl. Checked before each jsonl append (`commit_round_checkpoint` and legacy jsonl append).

**Orchestrator Wave 3 (P4+P7)**
- **P4:** After Builder, **`rag_context = _compact_leader_rag_context(get_rag_context(query_memory))`** runs **before** Compressor, Red Team, and Leader. Compressor and Red Team receive the **same** `rag_context`; Red Team user text also includes the **Compressor summary** (`compressor_output`); Leader still receives **full** `idea_expansion` (not only the compact mid-stage text).
- **P7:** **`ALPHA_STRICT_LEADER_JSON`** defaults to **on** (strict JSON). Set to **`0`** to restore the prior loose Leader path (`temperature=0.2`). Strict mode uses **`temperature=0`**, one repair attempt, then either failure state **`ledger_delta: leader_json_parse_failed`** with **`parse_error: true`** (baton stays on current task) or, if **`ALPHA_ALLOW_PROSE_LEADER_BATON=1`**, the legacy prose fallback.

