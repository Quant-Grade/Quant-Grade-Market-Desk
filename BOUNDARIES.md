# BOUNDARIES — RAG_SYSTEM import and write-scope contract

**Status:** active contract, enforced by `tools/check_boundaries.py`.
**Version:** 1.
**Applies to:** everything under this repository (RAG_SYSTEM only).

This document names the one-way seam between the **alpha loop** and the **product RAG** subsystems, and declares which code may import what and which code may write to which on-disk artifacts. It is not aspirational. The paired grep tool `tools/check_boundaries.py` asserts the current state of the tree against these rules; any violation is a failure, not a warning.

`check_boundaries.py` MUST be run as part of `tools/verify_all.py` once that lands (S4). Until then it is runnable standalone: `python -X utf8 tools\check_boundaries.py`.

---

## 1. Ownership zones

### Zone A — Alpha loop (theory-crafting engine)
- **Owner:** `orchestrator.py` at repo root.
- **Writes (exclusive):** `idea_log.md`, `theory_log.md`, `rag_system_v2/data/alpha_concepts.jsonl`, `rag_system_v2/data/scribe_ledger.jsonl`, `rag_system_v2/data/alpha_concepts_chunks.jsonl`, `rag_system_v2/data/archive/alpha_concepts_*.jsonl`, `rag_system_v2/data/qdrant_alpha/**`, `rag_system_v2/data/bm25_alpha_index.pkl`, `rag_system_v2/data/embedding_cache_alpha/**`.
- **Envelope contract:** `scribe_ledger.jsonl` (`"v": 1`, prospective `"v": 2`), `theory_log.md` (`theory_log_version: 1`), `alpha_concepts.jsonl` (envelope bump pending S3a).

### Zone B — Product RAG (retrieval pipeline)
- **Owner:** `rag_system_v2/src/**`.
- **Writes (exclusive):** `rag_system_v2/data/chunks.jsonl`, `rag_system_v2/data/bm25_index.pkl`, `rag_system_v2/data/qdrant/**`, `rag_system_v2/data/parents.sqlite`, `rag_system_v2/data/manifest.json`, `rag_system_v2/data/embedding_cache/**`, `rag_system_v2/logs/query_trace.jsonl`, `rag_system_v2/reports/**`.
- **Envelope contract:** `manifest.json` (`"schema_version": 2`, prospective `3` in S2).

### Zone C — Harnesses and tools
- **Members:** `tools/**`, `artifacts/verification/**` (Python files only), `rag_system_v2/tests/**`.
- **Writes:** only to tempdirs the harness itself creates, and to `artifacts/verification/*.md`, `artifacts/verification/*.txt`, `artifacts/verification/gate2_*/**`, `artifacts/verification/blind_spots_*.md`, `artifacts/verification/baseline_*.md`, `artifacts/verification/doctor_baseline_*.txt`, `artifacts/verification/_resume_proof_*`, `artifacts/verification/_resume_after_fail_proof_*`.
- **Never writes to:** any Zone A or Zone B runtime artifact.

### Zone D — Historical / inert
- **Members:** `orchestrator.py.pre_hardening`, `idea_log.md.tmp` (pre-Round-85 residue), `SMG-OS.txt`, any `*.bak_*` timestamped backup.
- **Rules:** not importable; not runtime. `check_boundaries.py` ignores them. They exist for provenance, not execution. Deletion of any Zone D member is its own decision; touching them in passing is forbidden.

---

## 2. Allowed imports (directed, one-way)

Rows are importers; columns are import targets.

| Importer | may import | must not import |
|---|---|---|
| **Zone A** (`orchestrator.py`) | `src.router`, `src.retrieve`, `src.query_alpha_memory` (read-only runtime retrieval) | any other `src.*` module (`serve_cli`, `ingest`, `build_all`, `eval`, `index_*`, `doctor`, `verify`, `prompting`, `merge_rrf`, `rerank`, `config` direct, `repo_paths` direct, `logging_config`) |
| **Zone B** (`rag_system_v2/src/*`) | internal `src.*` siblings (relative imports) | `orchestrator` (ANY reference — no alpha loop visibility) |
| **Zone C** (`tools/**`, `artifacts/verification/*.py`, `rag_system_v2/tests/**`) | `orchestrator`, any `src.*`, any internal helper | production surfaces in a way that mutates Zone A or Zone B artifacts |
| **Zone D** | N/A | N/A (not imported by anything; not runtime) |

### Rationale

- **Zone A's three imports are the entire product-surface it consumes.** They are the read-only retrieval + alpha-self-memory path. Anything more would couple the theory loop to ingest, generation, or citation — which are product concerns the alpha loop never orchestrates.
- **Zone B's hard no-import of orchestrator** is the invariant that keeps `serve_cli` a shippable product. Any regression here would make the product unable to stand alone.
- **Zone C is deliberately permissive.** Harnesses need to reach into both sides to prove behavior. Their restriction is on write scope, not read scope.

---

## 3. Forbidden writes (by zone)

| Zone | Must NOT write to |
|---|---|
| A (Alpha) | `chunks.jsonl`, `bm25_index.pkl`, `qdrant/**`, `parents.sqlite`, `manifest.json`, `embedding_cache/**`, `logs/query_trace.jsonl`, `reports/**` |
| B (Product) | `idea_log.md`, `theory_log.md`, `alpha_concepts.jsonl`, `alpha_concepts_chunks.jsonl`, `scribe_ledger.jsonl`, `qdrant_alpha/**`, `bm25_alpha_index.pkl`, `embedding_cache_alpha/**`, `archive/alpha_concepts_*.jsonl` |
| C (Tools) | any of the above outside of tempdirs |
| D (Historical) | anything (not runtime) |

Filename namespacing (product = bare; alpha = `_alpha` or `alpha_` prefix; qdrant = `qdrant/` vs `qdrant_alpha/`) is part of the contract. New artifacts introduced by either zone must follow this convention.

---

## 4. `data/` per-file ownership manifest

Files currently under `rag_system_v2/data/`:

| File / directory | Owner | Writer | Reader(s) |
|---|---|---|---|
| `chunks.jsonl` | Zone B | `ingest.py` / `build_all.py` | `retrieve.py`, `doctor.py`, `verify.py` (via chunk lookup), indirect readers of `Retriever` |
| `bm25_index.pkl` | Zone B | `index_bm25.py` / `build_all.py` | `retrieve.py`, `doctor.py` (via `BM25Index.load`) |
| `qdrant/` | Zone B | `index_qdrant.py` / `build_all.py` | `retrieve.py`, `doctor.py` |
| `parents.sqlite` | Zone B | `ingest.py` | `retrieve.py`, `doctor.py` |
| `manifest.json` | Zone B | `build_all.py` | `doctor.py`, advisory consumers |
| `embedding_cache/` | Zone B | `index_qdrant.py` / embedding model | `index_qdrant.py` on re-embed |
| `alpha_concepts.jsonl` | Zone A | `orchestrator.py:commit_round_checkpoint` | `orchestrator.py` (resume, state summary), harnesses |
| `scribe_ledger.jsonl` | Zone A | `orchestrator.py:_append_scribe_ledger` | future chain-verify sidecar (not yet built) |
| `alpha_concepts_chunks.jsonl` | Zone A | alpha ingest (`ingest_alpha_concepts.py`) | `query_alpha_memory.py` |
| `qdrant_alpha/` | Zone A | `index_alpha_memory.py` | `query_alpha_memory.py` |
| `bm25_alpha_index.pkl` | Zone A | alpha BM25 builder | `query_alpha_memory.py` |
| `embedding_cache_alpha/` | Zone A | alpha embedder | alpha indexer |
| `archive/alpha_concepts_*.jsonl` | Zone A | `orchestrator.py:maybe_rotate_alpha_jsonl` | operator review only |
| `logs/query_trace.jsonl` | Zone B | `serve_cli.py:TraceLogger.log` | operator review, future eval harness |
| `reports/` | Zone B | `eval.py` | operator review |

Several current-on-disk state notes:
- `bm25_alpha_index.pkl` and `alpha_concepts_chunks.jsonl` are zero bytes (alpha self-memory side-files not rebuilt). Ownership is declared even though data is currently empty.
- `manifest.json` stores absolute paths referencing a previous machine root (`C:\\GitHub\\RAG_SYSTEM\\…`). Will be rebuilt to repo-relative paths in S2 with `schema_version: 3`.

---

## 5. `.env` precedence (supporting note, referenced by S1a)

There is exactly one `.env` read by live code: `RAG_SYSTEM/.env` at repo root.

- `orchestrator.py:57 _load_env_file(env_path)` uses `env_path = _script_dir / ENV_FILENAME` where `_script_dir = Path(__file__).resolve().parent` — i.e., the directory containing `orchestrator.py`. That is the repo root.
- `orchestrator.py:51–55`: `from dotenv import load_dotenv` then `load_dotenv(env_path)` with the same `env_path`, when python-dotenv is available.
- `rag_system_v2/src/config.py` uses per-variable `os.getenv(...)` at field-default time; it does not call `load_dotenv()` itself. It inherits whatever the parent process already put into `os.environ`.

**Practical rules:**
1. The sole authoritative `.env` is the one next to `orchestrator.py`.
2. If `serve_cli` is invoked without `orchestrator.py` having run first, it will rely on the caller's `os.environ`. Operator-facing launchers (`start.ps1`, `start.bat`, `start.sh`) are responsible for sourcing `.env` in that case.
3. There is no `.env` inside `rag_system_v2/`. Anything that appears to reference one is docs drift and must be corrected.

---

## 6. Enforcement

`tools/check_boundaries.py` MUST pass for any commit that modifies code. Its checks:

1. No file under `rag_system_v2/src/**` contains `import orchestrator` or `from orchestrator`.
2. `orchestrator.py` imports from `src.*` only via the three approved targets: `src.router`, `src.retrieve`, `src.query_alpha_memory`. Any other `from src.X` or `import src.X` is a violation.
3. No Python file under `rag_system_v2/src/**` imports any root-level script (`inspect_alpha_concepts`, `inspect_state_tracker`, `smoke_alpha_round`).
4. `orchestrator.py.pre_hardening` and other Zone D files are explicitly excluded from analysis; their presence in the tree is not an import-graph concern.

On violation, the tool prints a named reason code and exits non-zero.

---

## 7. Change discipline

- Adding a new approved import target for Zone A requires updating this document AND `tools/check_boundaries.py` AND the import site, in that order, in the same PR.
- Retiring an approved import target is the reverse: update the tool to reject it, then remove the import, then update this document.
- Zone crossings that are "documentation references only" (e.g., `MASTER_PLAN.md` naming a source file) are not import-graph concerns and do not need `check_boundaries.py` edits.
- New files added to Zone D (historical snapshots, backups, text dumps) must either match the exclusion patterns the tool already uses or be added to its exclusion list in the same PR.

---

## 8. What this document does NOT do

- It does not replace `SCHEMAS.md` (which will land in S2 as the envelope-version registry).
- It does not freeze the private-symbol surface of `orchestrator.py`; that is `API_CONTRACT.md`'s job in S6.
- It does not govern runtime behavior — only source-code imports and on-disk write scope.
- It does not attempt to enforce semantic boundaries beyond imports (e.g., "Zone A must only call read-methods of Zone B"). That would be runtime-level enforcement; grep-level enforcement is sufficient for the current scope.

---

## 9. Current state at this document's landing

Verified by `tools/check_boundaries.py` at the time of this PR:
- Zone B → Zone A imports: **0**.
- Zone A → Zone B imports: exactly three approved targets in `orchestrator.py`, all inside function bodies with fallback error handling.
- Zone C imports: 4 wave harnesses in `tools/` + 1 proof harness in `artifacts/verification/`.
- Zone D files (`orchestrator.py.pre_hardening`, `idea_log.md.tmp`, `SMG-OS.txt`, `*.bak_*`) excluded from analysis.

The contract describes the current tree, not a future aspiration.
