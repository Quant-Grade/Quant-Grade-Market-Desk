"""
Proof A (deterministic): non-baton governance failure never triggers baton sync;
debug clause logs expected code; checkpoint record shape matches fail-closed contract.

Run from repo root:
  python -X utf8 artifacts/verification/governance_foundation_proof_a.py

No LM calls. Imports orchestrator after setting env.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if not (REPO_ROOT / "orchestrator.py").exists():
    print(
        "PROOF_A_FAIL expected orchestrator.py under",
        REPO_ROOT,
        file=sys.stderr,
    )
    sys.exit(1)
sys.path.insert(0, str(REPO_ROOT))


def _base_gov_obj() -> dict:
    return {
        "core_objective_anchor": "anchor",
        "ledger_delta": "delta",
        "highest_active_risk": "risk",
        "baton_pass": {"next_task": "aligned task text"},
        "governance_options": [
            {
                "id": "opt-a",
                "summary": "one",
                "next_task": "aligned task text",
                "confidence": 0.5,
                "collateral_risk": 0.3,
            },
            {
                "id": "opt-b",
                "summary": "two",
                "next_task": "other task",
                "confidence": 0.4,
                "collateral_risk": 0.2,
            },
        ],
        "selected_option_id": "opt-a",
    }


def main() -> None:
    os.environ["ALPHA_GOVERNANCE_OPTIONS"] = "1"
    os.environ["ALPHA_DEBUG_GOV"] = "1"
    os.environ["ALPHA_NO_COLOR"] = "1"

    import orchestrator as orch

    failures: list[str] = []

    # --- score_range (not baton_mismatch) ---
    obj_sr = _base_gov_obj()
    obj_sr["governance_options"][0]["confidence"] = 1.5
    code = orch._leader_governance_diagnose(obj_sr)
    if code != "score_range":
        failures.append(f"expected score_range, got {code!r}")
    if orch._try_governance_baton_sync_if_only_mismatch(dict(obj_sr)) is not False:
        failures.append("baton sync should not run for score_range")

    buf = io.StringIO()
    with redirect_stdout(buf):
        orch._debug_governance_log_clause(obj_sr)
    log_out = buf.getvalue()
    if "governance_validation_clause" not in log_out or "score_range" not in log_out:
        failures.append(f"debug log missing clause; got: {log_out!r}")

    fs = orch._leader_governance_fail_state("seed task")
    if fs.get("ledger_delta") != "governance_validation_failed":
        failures.append("fail_state ledger_delta")
    if fs.get("governance_parse_error") is not True:
        failures.append("fail_state governance_parse_error")
    if fs.get("baton_pass", {}).get("next_task") != "seed task":
        failures.append("fail_state baton hold")
    rec = orch.build_alpha_checkpoint_record(
        1,
        "seed task",
        "",
        "",
        "",
        "",
        "seed task",
        json.dumps(fs, ensure_ascii=False),
        "",
        "",
    )
    st = rec.get("state_tracker")
    if not isinstance(st, dict) or st.get("ledger_delta") != "governance_validation_failed":
        failures.append("checkpoint state_tracker does not reflect fail-closed")

    # --- option_count (single option) ---
    obj_oc = _base_gov_obj()
    obj_oc["governance_options"] = [obj_oc["governance_options"][0]]
    if orch._leader_governance_diagnose(obj_oc) != "option_count":
        failures.append("expected option_count")
    if orch._try_governance_baton_sync_if_only_mismatch(dict(obj_oc)) is not False:
        failures.append("baton sync should not run for option_count")

    # --- baton_mismatch: sync may apply (sanity that fixture differs from non-baton path) ---
    obj_bm = _base_gov_obj()
    obj_bm["baton_pass"] = {"next_task": "wrong baton"}
    if orch._leader_governance_diagnose(obj_bm) != "baton_mismatch":
        failures.append("expected baton_mismatch for control fixture")
    before = obj_bm["baton_pass"]["next_task"]
    sync_log = io.StringIO()
    with redirect_stdout(sync_log):
        synced = orch._try_governance_baton_sync_if_only_mismatch(obj_bm)
    sync_out = sync_log.getvalue()
    if "baton_synced_from_governance" not in sync_out or "applied" not in sync_out:
        failures.append(f"baton sync log missing; got {sync_out!r}")
    if not synced:
        failures.append("baton sync should repair baton_mismatch fixture")
    after = obj_bm["baton_pass"]["next_task"]
    if after == before:
        failures.append("baton next_task unchanged after sync")
    if orch._leader_governance_diagnose(obj_bm) is not None:
        failures.append("after sync, governance should validate")

    if failures:
        print("PROOF_A_FAIL", failures)
        sys.exit(1)
    print("PROOF_A_OK score_range option_count baton_mismatch_control checkpoint")


if __name__ == "__main__":
    main()
