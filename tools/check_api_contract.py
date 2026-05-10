"""
check_api_contract.py - Enforcement companion to API_CONTRACT.md.

Verifies that every symbol listed in API_CONTRACT.md §3 exists at module scope
in `orchestrator.py`. Runs the frozen contract against the current tree and
fails loud if any symbol has been renamed, removed, or moved out without a
re-export.

Usage:
    python -X utf8 tools/check_api_contract.py

Exit codes:
    0   every listed symbol exists
    1   one or more symbols missing (contract violation)
    2   internal error (cannot import orchestrator, etc.)

Named reason codes on violation:
    api_contract_missing_symbol <name>
    api_contract_import_failed

Change discipline: when API_CONTRACT.md §3 gains or loses a symbol, update
REQUIRED_SYMBOLS in the same PR. See API_CONTRACT.md §4.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


# REQUIRED_SYMBOLS: every symbol that API_CONTRACT.md §3 freezes.
# Order matches the documented sections (attributes, private fns, public fns).
# Adding/removing here requires a paired API_CONTRACT.md edit (see §4).
REQUIRED_SYMBOLS: tuple[str, ...] = (
    # §3.1 Module-level attributes (monkey-patchable)
    "_rag_v2_base",
    "IDEA_LOG_PATH",
    "THEORY_LOG_PATH",
    # §3.2 Private functions (underscored; frozen despite the underscore)
    "_require_operational_limits_or_exit",
    "_leader_governance_diagnose",
    "_try_governance_baton_sync_if_only_mismatch",
    "_debug_governance_log_clause",
    "_leader_governance_fail_state",
    # §3.3 Public functions
    "commit_round_checkpoint",
    "load_last_alpha_jsonl_record",
    "rebuild_last_round_texts_from_jsonl",
    "call_builder",
    "call_leader",
    "prepend_state_summary",
    "maybe_rotate_alpha_jsonl",
    "build_alpha_checkpoint_record",
    "main",
)


# LEGACY_ALIASES: symbols that have been renamed but must still be accessible
# by their old name for a deprecation window. See API_CONTRACT.md §4.2.
# Format: {old_name: new_name} — both must exist on the module during the window.
# Empty until the first rename happens.
LEGACY_ALIASES: dict[str, str] = {}


def main() -> int:
    # Ensure repo root is on sys.path so `import orchestrator` resolves.
    sys.path.insert(0, str(REPO_ROOT))

    try:
        mod = importlib.import_module("orchestrator")
    except Exception as e:
        print("api_contract_import_failed", type(e).__name__, str(e)[:200])
        return 2

    missing: list[str] = []
    for name in REQUIRED_SYMBOLS:
        if not hasattr(mod, name):
            missing.append(name)

    # Legacy-alias verification: both names must exist on the module.
    legacy_missing: list[str] = []
    for old_name, new_name in LEGACY_ALIASES.items():
        if not hasattr(mod, old_name):
            legacy_missing.append(f"legacy={old_name}")
        if not hasattr(mod, new_name):
            legacy_missing.append(f"new={new_name}")

    if missing or legacy_missing:
        for name in missing:
            print(f"api_contract_missing_symbol {name}")
        for item in legacy_missing:
            print(f"api_contract_legacy_alias_missing {item}")
        return 1

    total = len(REQUIRED_SYMBOLS)
    if LEGACY_ALIASES:
        total += 2 * len(LEGACY_ALIASES)
    print(f"api_contract_ok {total}_symbols_verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
