# RAG_SYSTEM — Copilot onboarding recap

**Purpose:** Single handoff for a new coding copilot: architecture, data, plans, risks, and suggested next moves. **Source of truth for repair rounds:** `Fix_plan.md` (read before substantive work).

**Last aligned with repo state:** loop foundation freeze (Rounds 74–83); `serve_cli` / Gate 2 path documented separately in `Fix_plan.md` Current State.

---

## 1. System at a glance

Two related systems live in one repo:

| Subsystem | Role | Primary entry |
|-----------|------|----------------|
| **`rag_system_v2/`** | Retrieval-augmented Q&A product: ingest → chunks → BM25 + Qdrant → router → rerank → `serve_cli` generation + verification | `python -X utf8 -m src.serve_cli` (needs indexes + LLM) |
| **Repo root `orchestrator.py`** | **Alpha / theory loop:** Builder → RAG context → Compressor → Red Team → Leader (JSON) → checkpoints; optional **A-lite governance** (scored options, baton sync, fail-closed) | `python -X utf8 orchestrator.py` (bounds via `ALPHA_MAX_ROUNDS` / wall clock) |

**Orchestrator** sets `RAG_V2_BASE_DIR` to `rag_system_v2` and prepends it to `sys.path` so it uses the same RAG stack for **memory retrieval** into the Leader/Builder path.

---

## 2. Repository tree (high level)

```
RAG_SYSTEM/
├── orchestrator.py          # Alpha loop (single file; governance, checkpoints, Leader JSON)
├── idea_log.md              # Human-readable round log (often gitignored locally)
├── Fix_plan.md              # Round ledger, gates, blockers (authoritative for repair work)
├── Recap.md                 # This file
├── CANONICAL_PATHS.json     # Path registry for docs/artifacts (IA phase)
├── .cursorrules             # Worker discipline for repo repair
├── artifacts/
│   └── verification/        # Narrow proof harnesses + optional proof logs/fixtures
└── rag_system_v2/
    ├── src/                 # Application code (config, router, retrieve, serve_cli, verify, …)
    ├── data/                # chunks.jsonl, bm25, qdrant, parents.sqlite, alpha_concepts.jsonl (often gitignored)
    ├── tests/test_smoke.py  # Smoke tests (currently drifted vs src — see Fix_plan)
    └── docs/                # Meta-prompts, loop notes
```

---

## 3. Corpus and how it is used

| Asset | Location (typical) | Use |
|--------|-------------------|-----|
| **Chunk store** | `rag_system_v2/data/chunks.jsonl` | Source text for retrieval |
| **BM25** | `rag_system_v2/data/bm25_index.pkl` | Lexical retrieval |
| **Qdrant** | `rag_system_v2/data/qdrant/` | Vector retrieval |
| **Parents** | `rag_system_v2/data/parents.sqlite` | Hierarchy / metadata |
| **Embeddings** | HF `BAAI/bge-small-en-v1.5` (cache under project) | Query/chunk vectors |
| **Alpha checkpoints** | `rag_system_v2/data/alpha_concepts.jsonl` | One JSON line per orchestrator round: task, expansions, Leader `state_tracker`, optional governance fields |
| **Alpha chunks mirror** | `alpha_concepts_chunks.jsonl` (if used) | Stricter doctor path — see Fix_plan deferred items |

**Orchestrator** does **not** re-ingest the whole corpus for theory crafting; it **queries** RAG via the same stack using `query_memory_for` from Builder. **Product** queries go through `serve_cli` with full pipeline.

---

## 4. What is currently planned (from `Fix_plan.md`)

- **Product critical path:** Stabilize **Gate 2** (`serve_cli`): first-pass verify, and **regen-under-fail** end-to-end proof still **open** (no reliable Step 5 fail + regen completion in-session per ledger).
- **Orchestrator foundation:** **Frozen for this phase** after governance proofs (fixture + N=3 + resume success + synthetic resume-after-fail + sanity run). Optional future: multi-line window resume proof; `compile_state_summary` context cap (diagnosed, not patched in freeze commit).
- **Deferred:** Smoke test alignment (8 failing tests vs current `src`), broad doctor/alpha_chunks policy, architecture refactors.

---

## 5. Future risks / failure modes

| Risk | Notes |
|------|--------|
| **Context pressure** | Leader / Compressor / RedTeam / **State of the Theory** (`compile_state_summary`) can hit LM **n_ctx**; orchestrator has compaction on some paths but **state summary** input is largely **unbounded**. |
| **Checkpoint hygiene** | Cold start **without** `ALPHA_RESUME=1` can **duplicate `round_id`** in `alpha_concepts.jsonl`; dim log warns if history exists. |
| **Governance ON** | Default **OFF**; when ON, baton sync only on `baton_mismatch`; non-baton failures fail-closed — regression: run `artifacts/verification/governance_foundation_proof_a.py`. |
| **Router / config drift** | Same query string can yield different router outcomes after threshold changes (`ASK_CLARIFY` vs `RETRIEVE_AND_ANSWER`). |
| **Smoke vs `src`** | `test_smoke.py` expectations may not match current config/API — **false red** until aligned. |
| **Secrets** | `.env` may hold API keys / webhooks — never commit. |

---

## 6. Five suggested next moves (with weighted confidence)

Each suggestion has **impact** if the rated part succeeds (0–100). Ratings are **evidence-informed guesses**, not guarantees.

### A. Gate 2 regen proof harness or forced-fail query (product path)

| Rated ingredient | Weight (impact if true) |
|------------------|-------------------------|
| Reproducible Step 5 fail | **85** |
| LM completes regen without timeout | **80** |
| **Overall suggestion value if executed well** | **High** |

---

### B. Cap `compile_state_summary` input (+ optional `max_tokens`) — orchestrator only

| Rated ingredient | Weight |
|------------------|--------|
| Confirms context error in logs first | **70** |
| Single-function truncation | **75** |
| **Overall** | **High** for stability, **low** blast |

---

### C. Align `test_smoke.py` to current `src` (package imports + config field names)

| Rated ingredient | Weight |
|------------------|--------|
| Fixes import style (`src` package) | **65** |
| Updates assertions to real `RouterConfig` / embedding fields | **70** |
| **Overall** | **Medium–high** for CI trust; **not** alpha-loop foundation |

---

### D. Optional: multi-line synthetic resume proof (`window` > 1)

| Rated ingredient | Weight |
|------------------|--------|
| Closes Round 81 footnote only | **55** |
| Low time cost | **80** |
| **Overall** | **Medium** EV, **narrow** foundation closure |

---

### E. Document / script: “spawn” checklist (env, bounds, backup before resume experiments)

| Rated ingredient | Weight |
|------------------|--------|
| Reduces operator error | **60** |
| **Overall** | **Medium**; cheap documentation win |

---

## 7. Commands reference (operator)

```text
# Alpha loop (bounded, example)
Set-Location <repo>\RAG_SYSTEM
$env:ALPHA_MAX_ROUNDS="1"
$env:ALPHA_NO_COLOR="1"
python -X utf8 orchestrator.py

# Governance regression (no LM for logic)
python -X utf8 artifacts\verification\governance_foundation_proof_a.py

# Product Gate 1 (import)
Set-Location <repo>\RAG_SYSTEM\rag_system_v2
python -X utf8 -c "from src.serve_cli import RAGOrchestrator; print('import_ok')"
```

---

## 8. Files a copilot should read first

1. `Fix_plan.md` — Current State + latest rounds  
2. `.cursorrules` — If doing repair work  
3. `orchestrator.py` — Env flags (`ALPHA_*`), `call_leader`, checkpoints  
4. `rag_system_v2/src/config.py` — Router and model defaults  
5. `CANONICAL_PATHS.json` — Doc paths  

---

*This recap does not replace `Fix_plan.md` for round-by-round truth. Update both when the leader changes phase or scope.*
