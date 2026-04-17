# Alpha Engine – Single-PC 4-Role Plan

## Goal

- Self-looping **Alpha Engine** on one local **LM Studio–compatible** endpoint (via `OpenAI` client in `orchestrator.py`) with four prompt-defined roles: **Builder**, **Compressor**, **RedTeam**, **Leader**.
- **Memory substrate:** `rag_system_v2` (main RAG stack). Optional **Alpha self-memory** when `ALPHA_USE_SELF_MEMORY=1` (separate indices; appended inside `get_rag_context`).
- **Durable artifacts:** human-readable **`idea_log.md`** (repo root beside `orchestrator.py`) and machine-readable **`rag_system_v2/data/alpha_concepts.jsonl`** (one JSON record per committed round, including `rag_context_snapshot` and checkpoint fields).

## Orchestrator runtime (current)

*Canonical contract — must match `orchestrator.py` and `ORCHESTRATOR_HARDENING_PLAN.md`.*

### Per-round pipeline

1. **Builder** — produces `idea_expansion` and `query_memory_for`.
2. **RAG** — `rag_context = _compact_leader_rag_context(get_rag_context(query_memory))` using the Builder’s query string. **The same** `rag_context` string is passed to Compressor, RedTeam, and Leader for that round.
3. **Compressor** — receives a **compacted** Builder expansion (`idea_for_mid`) and **`rag_context`**.
4. **RedTeam** — receives the **same** `rag_context`, the compacted Builder expansion, and the **Compressor summary** (`compressor_output`) in the user message.
5. **Leader** — receives **full** `idea_expansion` (not only the compact mid-stage text) and **`rag_context`**.

### Operational limits (P6)

Before any LM client is created: either `ALPHA_ALLOW_UNBOUNDED_LOOP=1`, or at least one of **`ALPHA_MAX_ROUNDS`** / **`ALPHA_MAX_WALL_SEC`** must be a **positive integer**. Otherwise the process **exits 2** with a stderr message.

### Resume (P2)

`ALPHA_RESUME=1` reads the **last** line of `rag_system_v2/data/alpha_concepts.jsonl`, sets `task` from `leader_next_task`, `round_num = last.round_id + 1`, and rebuilds `last_round_texts` from the jsonl tail (window **`ALPHA_RESUME_REBUILD_WINDOW`**, default **5**). Resume with an **empty** jsonl → **exit 3**.

### Baton to Builder (P3)

After each **successful** round commit, the next Builder call can include **`PRIOR_STATE_TRACKER`** and **`PRIOR_ORGANIZED_MEMORY`** from the prior round.

### Atomic persistence (P1)

Each round uses **`commit_round_checkpoint`**: jsonl append and `idea_log` append are committed together — **`round_num` / `task` advance only after** commit succeeds.

### State of the Theory prepend (P5)

`prepend_state_summary` writes **`idea_log.md.tmp`** then **`os.replace`** into `idea_log.md` (same directory).

### Retention (P8)

Optional **`ALPHA_JSONL_MAX_BYTES`** and/or **`ALPHA_JSONL_MAX_LINES`**. If the active `alpha_concepts.jsonl` exceeds a set threshold, it is moved to **`rag_system_v2/data/archive/alpha_concepts_<UTC>.jsonl`** before the next append.

### Leader JSON (P7)

Default **`ALPHA_STRICT_LEADER_JSON=1`**: strict JSON, `temperature=0`, schema validation, one repair pass. Persistent failure yields state with **`ledger_delta: leader_json_parse_failed`** and **`parse_error: true`** (baton stays on current task) unless **`ALPHA_ALLOW_PROSE_LEADER_BATON=1`** (legacy prose fallback). **`ALPHA_STRICT_LEADER_JSON=0`** restores the looser path (`temperature=0.2`).

### Model / endpoint

Typically **`ALPHA_MODEL_ID`** or **`LM_STUDIO_MODEL_ID`**; base URL configured in `orchestrator.py` (e.g. **`LMSTUDIO_BASE_URL`**).

## References

- **`CANONICAL_PATHS.json`** — machine-facing registry of canonical repo-relative paths (orchestrator entrypoint, RAG root, checkpoint jsonl, idea log, verification glob, `repo_paths` SSOT pointer). **Automation and tools should read this first.**
- **`COPILOT.md`** — guardrails, env history, Wave bullet summaries.
- **`ORCHESTRATOR_HARDENING_PLAN.md`** — full phase contract and verification checklist.
- **`fix_plan.md`** — round evidence for orchestrator phases.

## Doc process

- Read **`MASTER_PLAN.md`** before deep inspection or edits in a worker round.
- **`COPILOT.md`** is the scope/context guardrail (expanded over time; not limited to 5–10 lines).
