# SCHEMAS — on-disk envelope versioning registry

**Status:** active registry. Every versioned artifact in the repo must appear here.
**Applies to:** RAG_SYSTEM only (no external systems, no sibling projects).
**Companion docs:** `BOUNDARIES.md` (zones + import contract), `Audits/*.md` (rationale trail).
**Enforcement:** paired with `tools/check_boundaries.py` for import-graph rules. Schema-lint rules for envelope shape will land in `tools/verify_all.py` (S4).

Every durable on-disk artifact in this repo carries a version token so producers and readers can evolve independently and so drift is detected at parse time, not at downstream failure time.

---

## 1. Three-convention rule

There are exactly three envelope-key conventions in this repo. New artifacts must use whichever one matches their kind; introducing a fourth convention requires a `SCHEMAS.md` PR approved on its own merits.

| Convention | Token | Applies to | Rationale |
|---|---|---|---|
| **Config-file envelope** | `"schema_version": N` (integer) | Static config files written once per build or migration (`manifest.json`) | Mirrors common industry convention for single-object config files; long-form token is cheap when there is only one per file |
| **Line-record envelope** | `"v": N` (integer), **always the first key of the object** | Append-only JSONL where every line carries its own envelope (`scribe_ledger.jsonl`, and — pending S3a — `alpha_concepts.jsonl`) | Short-form token minimizes bytes-per-line; first-key positioning makes partial-read tolerance trivial (`line.startswith('{"v":N')`) |
| **Markdown-block envelope** | `<!-- <name>_version: N -->` as the first line of each block, plus additional YAML-frontmatter lines as needed | Append-only Markdown (`theory_log.md`, and — pending S3b — `idea_log.md` round sections) | HTML-comment headers are invisible when rendered, parseable by machines, and preserve Markdown readability for humans |

The three conventions are **non-interchangeable**. A line-record never uses `"schema_version"`. A config file never uses `"v"`. A Markdown file never uses JSON tokens.

---

## 2. Registry

### 2.1 `rag_system_v2/data/manifest.json` (config-file envelope)

- **Token:** `"schema_version": N` as first top-level key.
- **Current version:** **3** (active).
- **Writer:** `rag_system_v2/src/build_all.py::Manifest.create` (`SCHEMA_VERSION = 3`).
- **Reader:** `rag_system_v2/src/build_all.py::Manifest.verify`, `rag_system_v2/src/doctor.py::check_manifest` (via the Manifest class).
- **Fields (v3):** `schema_version`, `created_at`, `embedding_model`, `chunk_count`, `doc_count`, `hashes` (nested: `chunks_sha256`, `bm25_index_sha256`, `qdrant_collection_hash`, `parents_sha256`), `paths` (nested: `chunks`, `bm25`, `qdrant`, `parents`).
- **v3 change vs v2:** `paths` values stored as **POSIX strings relative to the manifest's own data_dir** (`"chunks.jsonl"`, `"bm25_index.pkl"`, `"qdrant"`, `"parents.sqlite"`) rather than absolute machine-specific paths (`"C:\\GitHub\\RAG_SYSTEM\\rag_system_v2\\data\\chunks.jsonl"`). Content-hash values are unchanged. `Manifest.verify` resolves paths via `self.data_dir / paths[...]`.
- **Legacy tolerance:** absolute paths from a legacy v2 manifest still resolve correctly because `Path(data_dir) / absolute_string` drops the left operand and returns the absolute path.
- **Reader rule:** missing `schema_version` → fail-closed `unknown_schema_version`. `schema_version != 3` → `Manifest.verify` already emits the explicit "Schema version mismatch" issue.

### 2.2 `rag_system_v2/data/scribe_ledger.jsonl` (line-record envelope)

- **Token:** `"v": N` as first key of each JSONL object.
- **Current version:** **1** (active). **v2 pending** (S3c will add `source_role` field; deferred).
- **Writer:** `orchestrator.py::_append_scribe_ledger`.
- **Reader:** operator inspection; future chain-verify sidecar (not yet built).
- **Fields (v1):** `v`, `ts_utc`, `round_id`, `task_sha256`, `disp` (currently always `"checkpoint_committed"`), `checkpoint_sha256`, `checkpoint_path_rel`.
- **v2 plan (S3c):** add `source_role` field naming which role authored the checkpoint (today always `"leader"`; forward-compatible for future deferred LM roles). Existing v1 entries on disk are grandfathered; readers must tolerate `v=1` (missing `source_role`) indefinitely.

### 2.3 `rag_system_v2/data/alpha_concepts.jsonl` (line-record envelope)

- **Token:** `"v": N` as first key of each JSONL object. **Currently missing.**
- **Current version:** **legacy (unversioned)**. **v1 pending** (S3a).
- **Writer:** `orchestrator.py::build_alpha_checkpoint_record` (called from `commit_round_checkpoint`).
- **Reader:** `orchestrator.py::load_last_alpha_jsonl_record` (resume), `rebuild_last_round_texts_from_jsonl` (resume-window), `compile_state_summary` (state-of-the-theory compiler, via call site).
- **Fields (legacy):** `round`, `round_id`, `timestamp`, `current_task`, `builder_expansion`, `query_memory_for`, `compressor_summary`, `redteam_attacks`, `leader_next_task`, `state_tracker`, `organized_memory`, `rag_context_snapshot`.
- **v1 plan (S3a):** add `"v": 1` as first key. No field changes. Readers treat missing `v` as legacy (accept) and unknown `v` as fail-closed `unknown_schema_version`.

### 2.4 `theory_log.md` (Markdown-block envelope)

- **Token:** `theory_log_version: N` as a YAML-frontmatter line inside `--- ... ---` at the start of each block.
- **Current version:** **1** (active, since Round 85).
- **Writer:** `orchestrator.py::prepend_state_summary` (appends new blocks; never rewrites existing).
- **Reader:** operator inspection; future state-of-the-theory replay tooling.
- **Block format:**
  ```
  ---
  theory_log_version: 1
  iso_utc: <ISO8601 Z>
  round_range: <lo>-<hi>
  ---

  <summary text>
  ```
- **Append-only:** never rewritten; `os.replace` is forbidden on this file.
- **Tested by:** `tools/verify_wave2.py::p5_prepend_atomic` (asserts frontmatter presence and append-only semantics).

### 2.5 `idea_log.md` round sections (Markdown-block envelope)

- **Token:** `<!-- round_section_version: N -->` as first line of each round block. **Currently missing.**
- **Current version:** **legacy (unversioned)**. **v1 pending** (S3b).
- **Writer:** `orchestrator.py::format_idea_log_round_section` (called from `commit_round_checkpoint`).
- **Reader:** operator inspection only. No machine reader currently parses round sections out of `idea_log.md`.
- **v1 plan (S3b):** add the HTML-comment header before each new `## Round <N>` block. Existing round sections on disk remain unchanged (append-only history).

### 2.6 Artifacts that are intentionally un-versioned

Not every on-disk artifact gets an envelope. The following are explicitly excluded and may remain unversioned:

- `rag_system_v2/data/chunks.jsonl` — ingestion output. Its per-line `schema_version: 2` field is owned by `ingest.py` and doctor validates it via `check_chunks_jsonl`. Treated as a Zone B internal schema, not part of this envelope registry.
- `rag_system_v2/data/bm25_index.pkl` — binary pickle. Version is implicit in `BM25Index.save`/`load` API contract.
- `rag_system_v2/data/parents.sqlite` — SQLite schema. Version is implicit in the CREATE TABLE statements.
- `rag_system_v2/data/qdrant/**` — Qdrant binary storage. Version is implicit in Qdrant's own format.
- `rag_system_v2/logs/query_trace.jsonl` — observability log. Consumers are forgiving by design (trace fields are advisory, not contractual).
- `rag_system_v2/data/archive/alpha_concepts_*.jsonl` — rotated from `alpha_concepts.jsonl`; inherits whatever envelope was in effect at the time of rotation.
- `artifacts/verification/*.md` and `*.txt` — point-in-time capture files. Their structure is prose + captured stdout, not machine-parsed contract.

Adding envelope versioning to any of the above requires its own PR with a `SCHEMAS.md` entry, a writer change, a reader change, and a reader-tolerance rule.

---

## 3. Reader-tolerance rule (applies to every envelope in §2)

Every reader of a versioned artifact **must** implement:

1. **Missing version token on a known-legacy artifact:** accept (legacy-era data predates the envelope; this is the grandfathering path). Record in the reader's internal state as "legacy" so downstream consumers can distinguish.
2. **Missing version token on an artifact expected to carry one:** fail-closed with reason code `missing_schema_version`. This covers the case where a writer regression stripped the envelope.
3. **Unknown version token (present but not in the current supported set):** fail-closed with reason code `unknown_schema_version`. This covers the case where a forward-version writer emits data a stale reader cannot safely parse.
4. **Type-drift on the version token** (e.g., `"v": "1"` string instead of `"v": 1` integer): fail-closed with reason code `schema_version_type_drift`. Envelope-lint in `tools/verify_all.py` (S4) will catch this proactively.

Readers may log a warning for legacy-accept (#1) and do log for cases #2–#4, but **must not silently downgrade** an unknown or mistyped version to legacy treatment.

---

## 4. Paper-only event type registrations

Event types that are documented here but have no live emitter yet. They are reserved for future use so downstream tooling does not need to be rebuilt when they light up.

| Event type | Target artifact | Current status | Intended emitter |
|---|---|---|---|
| `lm_model_mismatch` | `scribe_ledger.jsonl` (v2+) | **paper-only** — not emitted by any current code path. Reserved for the γ.2 LM arbitration layer when it lands beyond the current roadmap's S6 parking. | `alpha_core/lm_client.py::get_client` (future). Fires when `/v1/models` reports a loaded model id different from the per-role expected model id. |

Registering `lm_model_mismatch` here (without implementation) is intentional: it reserves the `disp` value so that a future Scribe v2+v3 schema evolution has a stable identifier to extend. Readers encountering this `disp` today will never see it; readers encountering it in the future will know its meaning is fixed by this registry.

---

## 5. Adding a new envelope version

Procedure, non-negotiable:

1. Land the schema change in `SCHEMAS.md` first (PR that updates the registry).
2. Land the writer change (emit the new token) — never in the same PR as step 1.
3. Land the reader-tolerance rule before step 2 merges — readers accept both old and new versions during the migration window.
4. If the schema change is additive (new field), old readers can continue to read new data (`extra="ignore"` is OK for the schema-version field itself only; downstream fields still demand explicit handling).
5. If the schema change is breaking (removed field, renamed field, changed type), coordinate a full migration: writer emits old+new for one release, then readers drop old tolerance, then writer drops old form.
6. Any schema PR ships with a corresponding `tools/verify_all.py` envelope-lint rule in the same PR (when `verify_all.py` exists).

---

## 6. Current-state attestation

As of this document's landing:

- `manifest.json` is at **v3** with data_dir-relative POSIX paths. Doctor validates it (`[+] Manifest valid (v3, 2296 chunks)`).
- `scribe_ledger.jsonl` is at **v1** with 2 historical entries. Last-pair hash verified against last `alpha_concepts.jsonl` line in the S0 baseline pass; first-pair entry is an orphan from pre-`ALPHA_RESUME` cold-start `round_id` duplication (known, non-blocking).
- `theory_log.md` is at **v1** — tested by `tools/verify_wave2.py::p5_prepend_atomic`.
- `alpha_concepts.jsonl` is **legacy-unversioned** — v1 envelope planned for S3a.
- `idea_log.md` round sections are **legacy-unversioned** — v1 envelope planned for S3b.
- `scribe_ledger.jsonl` v2 with `source_role` planned for S3c (not `role` — naming chosen to forward-compatibly distinguish "role that emitted this event" from the future "role holding baton authority" semantic).

The registry describes the current tree. Any divergence is a bug.
