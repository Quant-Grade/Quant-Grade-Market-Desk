# Gate 2 — Capture Classification

**Scope:** Classify all 11 `gate2_*.txt` captures under `artifacts/verification/` for terminal state.
**Mode:** Read-only analysis of existing captures. No new runs, no code changes.
**Purpose:** Determine whether Gate 2 (regen-under-fail end-to-end) is closable by curation of existing evidence, or whether a targeted proof is needed.
**Source files:** captures listed below, dated 2026-04-16 (one session).

---

## Per-capture table

| # | Capture | Router Decision | Confidence | Reasons | Step 5 ran? | Verify Status | Issues | Regen attempts | Terminal state |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `gate2_round31_capture.txt` | REFUSE_NO_EVIDENCE | 0.047 | `below_refuse_threshold` | no (skipped per design) | — | — | — | **REFUSE_NO_EVIDENCE (router)** |
| 2 | `gate2_round35_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | **RETRIEVE → PASS (first pass)** |
| 3 | `gate2_round36_capture.txt` | RETRIEVE_AND_ANSWER | 0.305 | `gray_zone_agreement_evidence`, `retriever_agreement` | yes | **fail** | **2** | **2 (both)** | **RETRIEVE → verify-fail → REGEN×2 → exhaustion-REFUSE** |
| 4 | `gate2_round37_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |
| 5 | `gate2_round38_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |
| 6 | `gate2_round39_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |
| 7 | `gate2_round39b_regen_stress.txt` | RETRIEVE_AND_ANSWER | 0.353 | `medium_high_confidence`, `retriever_agreement` | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass; stress-labeled but no regen triggered) |
| 8 | `gate2_round46_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |
| 9 | `gate2_round51_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |
| 10 | `gate2_round56_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |
| 11 | `gate2_round59_capture.txt` | RETRIEVE_AND_ANSWER | — | — | yes | pass | 0 | 0 | RETRIEVE → PASS (first pass) |

Confidence and reasons are listed where captured near the `Decision:` block.

## Summary

**Terminal-state counts across 11 captures:**

| Terminal state | Count | Captures |
|---|---|---|
| `RETRIEVE → first-pass PASS` | **9** | round35, round37, round38, round39, round39b_stress, round46, round51, round56, round59 |
| `REFUSE_NO_EVIDENCE` (router layer, Step 5 skipped by design) | **1** | round31 |
| `RETRIEVE → verify-fail → REGEN×2 → exhaustion-REFUSE` | **1** | round36 |
| `RETRIEVE → verify-fail → REGEN→PASS` (regen converges to cited answer) | **0** | none |

## Gate 2 terminal-state coverage

The product's reachable terminal states, per `serve_cli.py:process_query` + `verify.py`:

1. Router `REFUSE_NO_EVIDENCE` — covered by round31.
2. Router `ASK_CLARIFY` — **not in capture set** (not required for Gate 2 regen-under-fail concern).
3. Router `NO_RETRIEVAL` (chitchat/system command) — **not in capture set** (not required).
4. `RETRIEVE_AND_ANSWER` → first-pass verify `pass` → answer returned — covered 9×.
5. `RETRIEVE_AND_ANSWER` → first-pass verify `fail` → `FixAction.REGENERATE` → re-verify strict `pass` → "[Regenerated]" answer returned — **0 captures**.
6. `RETRIEVE_AND_ANSWER` → first-pass verify `fail` → `FixAction.REGENERATE` → both regen attempts fail → `MAX_REGENERATION_ATTEMPTS=2` exhaustion → "couldn't generate a properly cited response" REFUSE — covered by round36.
7. `RETRIEVE_AND_ANSWER` → first-pass verify `fail` → `FixAction.REFUSE` (direct refuse, no regen attempted) — **not in capture set** (untriggered terminal; not a current product concern).

## Gate 2 gap analysis

**Proven:**
- First-pass PASS: robust, reproducible, 9 independent captures across sessions round35–round59.
- Router REFUSE fail-closed: proven (round31).
- **Regen-exhaustion REFUSE: proven (round36).** The full regen cycle executes without hang, both attempts complete, the exhaustion-REFUSE terminal message fires cleanly. Total latency ~13 s. This is the hardest-to-prove safety terminal and it **is** proven.

**Not proven by existing captures:**
- **Regen→PASS**: no capture shows `REGENERATE` producing a cited answer that re-verifies as `pass` on retry. The path is coded in `serve_cli.py:352–378` (`if verification.is_acceptable(): break` after each attempt), but no recorded run has exercised it to a successful terminal.

## Safety vs. optimality

- **Safety terminal states are complete.** Every path the code can take that affects product correctness either (a) returns a verified cited answer, (b) refuses cleanly before generation, or (c) refuses cleanly after regen exhaustion. There is no path where an un-verified answer ships.
- **Optimality of regen is unproven.** We know regen either passes or exhausts; we do not have empirical evidence of the pass branch firing. The product is safe in either case; the question is whether regen is ever useful.

## Classification verdict

**Gate 2 is PARTIALLY closable by curation alone.**

- **Closable-by-curation claim:** "The product pipeline is end-to-end safe: every reachable retrieval path either delivers a cited answer or refuses, including exhaustion-REFUSE when regen does not converge."
- **Known remaining gap:** "Empirical demonstration that `FixAction.REGENERATE` can produce a re-verified cited answer on retry has not been captured."

## Decision for S5

Two defensible options:

### Option A — **Close on safety grounds now** (zero-cost closure)
- Publish the above classification as the Gate 2 proof.
- Document the unproven regen→PASS branch as a known optimality gap, not a safety gap.
- Emit a signed trace in Scribe envelope convention (once S3 lands) citing this classification file.
- Close Gate 2 with an explicit footnote.

### Option B — **Add one targeted regen→PASS capture** (minimal additive proof)
- Run a single bounded `serve_cli` query chosen to land in a gray-zone where the first-pass verify is likely to fail citation-completeness (multi-claim answer, partial citations) but where the stricter regen prompt ("Be very careful to cite every claim") is likely to succeed.
- Capture as `artifacts/verification/gate2_round_regen_pass.txt` (naming consistent with existing captures).
- Update this classification file with the new row and a "Regen→PASS: proven" line.
- Emit the signed trace.
- **Scope: exactly one capture, no code change, LM Studio already reachable per S0 doctor output (11 models available).** This is the narrowest legitimate targeted proof.

## Recommendation

**Option B.** Reasoning:
- The evidence ceiling for "Gate 2 closed" should include the regen-convergence branch empirically, not just theoretically. Code-path existence without empirical proof is the fragility that prior audits named.
- Cost is one bounded run on an already-reachable LM endpoint; no structural change.
- The result — success or failure — is informative either way. Success closes Gate 2 tightly. Failure (regen never converges on any query we try) is itself a decision-grade finding that promotes from "optimality gap" to "regen path may be effectively unusable in practice" and reframes the product claim.
- Option B is well-bounded: one capture file, no code diff, slotted into the same envelope pattern as all existing captures.

**Option A is defensible** if the operator's stance is "safety is enough, optimality is out of Gate 2 scope." The choice is the operator's.

## Effect on S5

- If Option A: S5 reduces to **publication** — write the conclusion and emit the Scribe-envelope signed trace after S3 lands. No new captures, no golden set.
- If Option B: S5 is **publication + one targeted capture** — the targeted capture lands first; this classification file is updated with the new row; the signed trace references both this file and the new capture.

Either way, S5 scope is materially narrower than "build a 5–10 query golden adversarial set." The 11 existing captures already close 3 of the 4 reachable Gate-2-relevant terminal states.

## Data quality notes

- All 11 captures are from the same 2026-04-16 session window.
- `C:\GitHub\RAG_SYSTEM` appears in log lines — the configuration loader still emits the pre-move absolute path in its INFO log, which does not affect runtime (config uses `default_rag_v2_base_dir()` resolution) but is a cosmetic artifact consistent with the stale-path finding in `manifest.json`.
- Captures are plain-text with ANSI escape sequences visible (`ΓòÉ`, `ΓûêΓûêΓûê`, etc.) — Windows console rendering; no semantic impact on classification.
- `gate2_round39b_regen_stress.txt` is labeled "regen_stress" but the captured run shows first-pass PASS — the stress test did not trigger verify failure on that query. So it is counted as a first-pass-PASS capture, with the note that a stress *attempt* was made.

## Files consumed

All under `artifacts/verification/`:
- `gate2_round31_capture.txt`, `gate2_round35_capture.txt`, `gate2_round36_capture.txt`, `gate2_round37_capture.txt`, `gate2_round38_capture.txt`, `gate2_round39_capture.txt`, `gate2_round39b_regen_stress.txt`, `gate2_round46_capture.txt`, `gate2_round51_capture.txt`, `gate2_round56_capture.txt`, `gate2_round59_capture.txt`.

No file was modified. Grep + targeted reads only.

## Next action (operator decision required)

Choose Option A (zero-cost closure, safety-only claim) or Option B (one targeted run to close the regen→PASS gap empirically). Both are inside the current approved roadmap for S5; neither requires a new initiative.
