"""
verify_all.py - Combined regression gate for RAG_SYSTEM.

Aggregates every green-gated harness plus structural checks into one exit code.
Runs each check as a subprocess so failures are isolated (a crash in one gate
does not prevent the others from running), and reports per-gate status.

Exit code convention:
    0   every gated check passed
    1   one or more gated checks failed
    2   internal error (a harness file is missing, Python invocation broken, etc.)

Advisory checks (optional, reported but not gated) are listed in ADVISORY; the
smoke suite is gated now that S4b + injection-pattern coverage are green.

Usage:
    python -X utf8 tools/verify_all.py [--quiet]

Companion docs: REGRESSION_NET.md (what each gate covers), SCHEMAS.md (envelope
versions that gate emissions conform to), BOUNDARIES.md (import/write zones
that check_boundaries.py enforces).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class Check:
    __slots__ = ("name", "cmd", "cwd", "purpose")

    def __init__(self, name: str, cmd: list[str], cwd: Path, purpose: str):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.purpose = purpose


# Green-gated: exit non-zero on any failure
GATED: tuple[Check, ...] = (
    Check(
        "P1 atomic commit",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "verify_p1_atomic_commit.py")],
        REPO_ROOT,
        "commit_round_checkpoint: atomic pair (alpha_concepts + idea_log) with byte-length rollback on failure.",
    ),
    Check(
        "Wave 1 (P6 + P2 + P3)",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "verify_wave1.py")],
        REPO_ROOT,
        "P6 operational bounds gate, P2 resume, P3 baton (prior_state_tracker + prior_organized_memory).",
    ),
    Check(
        "Wave 2 (P5 + P8)",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "verify_wave2.py")],
        REPO_ROOT,
        "P5 theory_log append-only (Round-85 contract), P8 alpha_concepts.jsonl rotation.",
    ),
    Check(
        "Wave 3 (P4 + P7)",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "verify_wave3.py")],
        REPO_ROOT,
        "P4 round-flow ordering (Builder -> RAG -> Compressor -> RedTeam -> Leader), P7 strict-JSON Leader with repair.",
    ),
    Check(
        "Proof A (governance)",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "artifacts" / "verification" / "governance_foundation_proof_a.py")],
        REPO_ROOT,
        "A-lite governance foundation: score range, option count, baton_mismatch sync control, checkpoint shape.",
    ),
    Check(
        "check_boundaries",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "check_boundaries.py")],
        REPO_ROOT,
        "Zone import contract (BOUNDARIES.md): product must not import orchestrator; orchestrator imports only 3 approved src.* targets; no product imports of root one-off scripts.",
    ),
    Check(
        "check_api_contract",
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "check_api_contract.py")],
        REPO_ROOT,
        "Frozen-surface contract (API_CONTRACT.md): every symbol wave harnesses + Proof A depend on exists at orchestrator module scope. Catches silent rename/removal of private-but-contractual symbols.",
    ),
    Check(
        "doctor",
        [sys.executable, "-X", "utf8", "-m", "src.doctor"],
        REPO_ROOT / "rag_system_v2",
        "rag_system_v2 health: manifest v3, chunks validity, BM25 load, parents DB, Qdrant, ID consistency, query latency, LM Studio reachability.",
    ),
    Check(
        "smoke suite",
        [sys.executable, "-X", "utf8", "-m", "pytest", "rag_system_v2/tests/test_smoke.py", "-q"],
        REPO_ROOT,
        "Foundation invariants: chunk-id determinism, hash, BM25, router enums, verifier fail-closed, config thresholds, manifest schema, embedding dims, injection detector, RRF merge.",
    ),
)


# Advisory: optional checks; empty until a new deferred harness is listed.
ADVISORY: tuple[Check, ...] = ()


def _run(check: Check, quiet: bool) -> tuple[str, int, float, str]:
    """Run one check; return (status, returncode, elapsed_seconds, tail_output)."""
    start = time.perf_counter()
    try:
        r = subprocess.run(
            check.cmd,
            cwd=str(check.cwd),
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return ("TIMEOUT", -1, elapsed, "(timeout after 600s)")
    except FileNotFoundError as e:
        elapsed = time.perf_counter() - start
        return ("MISSING", 2, elapsed, f"{e}")
    elapsed = time.perf_counter() - start
    status = "PASS" if r.returncode == 0 else "FAIL"
    tail = (r.stdout or "").strip().splitlines()[-4:] + (r.stderr or "").strip().splitlines()[-2:]
    return (status, r.returncode, elapsed, "\n    ".join(tail[-6:]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Combined regression gate for RAG_SYSTEM.")
    parser.add_argument("--quiet", action="store_true", help="suppress per-check tail output")
    args = parser.parse_args()

    print("=" * 72)
    print("RAG_SYSTEM verify_all — gated checks")
    print("=" * 72)

    gated_failures = 0
    internal_errors = 0
    for check in GATED:
        status, rc, elapsed, tail = _run(check, args.quiet)
        marker = "[+]" if status == "PASS" else "[x]"
        print(f"  {marker} {check.name}  ({elapsed:.1f}s, rc={rc})")
        if status != "PASS":
            if status == "MISSING":
                internal_errors += 1
            else:
                gated_failures += 1
            if not args.quiet and tail.strip():
                print(f"    ---")
                for line in tail.split("\n"):
                    print(f"    {line}")

    print()
    advisory_failures = 0
    if ADVISORY:
        print("-" * 72)
        print("Advisory (not gated)")
        print("-" * 72)
        for check in ADVISORY:
            status, rc, elapsed, tail = _run(check, args.quiet)
            marker = "[+]" if status == "PASS" else "[~]"
            print(f"  {marker} {check.name}  ({elapsed:.1f}s, rc={rc}){'  [advisory]' if status != 'PASS' else ''}")
            if status != "PASS":
                advisory_failures += 1
                if not args.quiet and tail.strip():
                    print(f"    ---")
                    for line in tail.split("\n"):
                        print(f"    {line}")
        print()

    print()
    print("=" * 72)
    if internal_errors > 0:
        print(f"verify_all_internal_error  gated_missing={internal_errors}")
        return 2
    if gated_failures > 0:
        print(f"verify_all_failed  gated_failures={gated_failures}  advisory_failures={advisory_failures}")
        return 1
    print(f"verify_all_ok  advisory_failures={advisory_failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
