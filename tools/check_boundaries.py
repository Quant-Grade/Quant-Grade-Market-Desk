"""
check_boundaries.py - Grep/AST enforcement companion to BOUNDARIES.md.

Enforced rules (see BOUNDARIES.md section 6):
  1. No file under rag_system_v2/src/** imports `orchestrator` (any form).
  2. orchestrator.py imports from src.* only via the three approved targets:
     src.router, src.retrieve, src.query_alpha_memory.
  3. No file under rag_system_v2/src/** imports root-level one-off scripts
     (inspect_alpha_concepts, inspect_state_tracker, smoke_alpha_round).
  4. Zone D files (historical snapshots, backups, text dumps) are excluded
     from analysis.

Usage:
    python -X utf8 tools/check_boundaries.py

Exit codes:
    0  all checks pass
    1  one or more boundary violations found
    2  internal error (bad file, AST parse failure in an included file, etc.)

Named reason codes on violation (printed verbatim, one per violation):
    product_imports_orchestrator
    orchestrator_imports_unapproved_src
    product_imports_root_oneoff
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_PATH = REPO_ROOT / "orchestrator.py"
PRODUCT_SRC_DIR = REPO_ROOT / "rag_system_v2" / "src"

# Orchestrator is allowed to import from exactly these three src modules.
APPROVED_SRC_TARGETS = {
    "src.router",
    "src.retrieve",
    "src.query_alpha_memory",
}

# Root-level one-off scripts that product code must not import.
ROOT_ONEOFF_NAMES = {
    "inspect_alpha_concepts",
    "inspect_state_tracker",
    "smoke_alpha_round",
}

# Zone D exclusions: historical files, backups, text dumps.
# Applied as substring match against the resolved path.
ZONE_D_PATTERNS = (
    ".pre_hardening",
    ".bak_",
    ".md.tmp",
    "SMG-OS.txt",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
)


def is_zone_d(path: Path) -> bool:
    """Check whether a path is a Zone D (historical/inert) file."""
    s = str(path)
    return any(pat in s for pat in ZONE_D_PATTERNS)


def _module_names_from_node(node: ast.AST) -> list[str]:
    """Extract all imported module names (top-level) from a single AST node."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        # `from X import Y` -> X is the module
        # `from X.Y import Z` -> X.Y is the module
        if node.module is not None:
            names.append(node.module)
    return names


def extract_imports(py_file: Path) -> list[str]:
    """Parse a Python file and return a list of imported module names.

    Captures both top-level and nested (function-body) imports equally; the
    boundary contract applies regardless of import depth.
    """
    src = py_file.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(py_file))
    imports: list[str] = []
    for node in ast.walk(tree):
        imports.extend(_module_names_from_node(node))
    return imports


def iter_product_src_py_files() -> list[Path]:
    """Return every .py file under rag_system_v2/src, excluding Zone D."""
    out: list[Path] = []
    if not PRODUCT_SRC_DIR.is_dir():
        return out
    for p in PRODUCT_SRC_DIR.rglob("*.py"):
        if is_zone_d(p):
            continue
        out.append(p)
    return out


def check_product_does_not_import_orchestrator() -> list[str]:
    """Rule 1: no product file imports orchestrator."""
    violations: list[str] = []
    for py in iter_product_src_py_files():
        try:
            mods = extract_imports(py)
        except SyntaxError as e:
            violations.append(
                f"[error] product_src_parse_failure {py.relative_to(REPO_ROOT)}: {e}"
            )
            continue
        for m in mods:
            top = m.split(".", 1)[0]
            if top == "orchestrator":
                violations.append(
                    f"product_imports_orchestrator "
                    f"{py.relative_to(REPO_ROOT)}: imports {m!r}"
                )
    return violations


def check_orchestrator_only_approved_src_imports() -> list[str]:
    """Rule 2: orchestrator.py only imports the three approved src.* targets."""
    violations: list[str] = []
    if not ORCHESTRATOR_PATH.is_file():
        return violations
    try:
        mods = extract_imports(ORCHESTRATOR_PATH)
    except SyntaxError as e:
        return [f"[error] orchestrator_parse_failure: {e}"]
    for m in mods:
        if not m.startswith("src."):
            continue
        if m not in APPROVED_SRC_TARGETS:
            violations.append(
                f"orchestrator_imports_unapproved_src "
                f"orchestrator.py: imports {m!r} (approved: "
                f"{sorted(APPROVED_SRC_TARGETS)})"
            )
    return violations


def check_product_does_not_import_root_oneoffs() -> list[str]:
    """Rule 3: product files must not import root-level one-off scripts."""
    violations: list[str] = []
    for py in iter_product_src_py_files():
        try:
            mods = extract_imports(py)
        except SyntaxError:
            continue  # already reported in rule 1
        for m in mods:
            top = m.split(".", 1)[0]
            if top in ROOT_ONEOFF_NAMES:
                violations.append(
                    f"product_imports_root_oneoff "
                    f"{py.relative_to(REPO_ROOT)}: imports {m!r}"
                )
    return violations


def main() -> int:
    all_violations: list[str] = []
    all_violations.extend(check_product_does_not_import_orchestrator())
    all_violations.extend(check_orchestrator_only_approved_src_imports())
    all_violations.extend(check_product_does_not_import_root_oneoffs())

    if not all_violations:
        print("boundaries_ok")
        return 0

    print("boundaries_violations_found", len(all_violations))
    for v in all_violations:
        print(v)
    # Distinguish internal errors (exit 2) from genuine violations (exit 1).
    if any(v.startswith("[error]") for v in all_violations):
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
