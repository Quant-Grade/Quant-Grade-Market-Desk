import inspect
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o


def _env_snapshot(keys):
    return {k: os.environ.get(k) for k in keys}


def _env_restore(snap):
    for k, v in snap.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def p4_main_loop_order():
    src = inspect.getsource(o.main)
    loop = src.split("while True:", 1)[1]
    i_rag = loop.index("rag_context = _compact_leader_rag_context(get_rag_context(query_memory))")
    i_comp = loop.index("ROLE_COMPRESSOR")
    i_red = loop.index("ROLE_REDTEAM")
    i_lead = loop.index("ROLE_LEADER")
    assert i_rag < i_comp < i_red < i_lead
    assert "compressor_output=compressor_output" in loop
    assert "rag_context=rag_context" in loop
    print("p4_order_ok")


def p7_strict_parse_fail():
    keys = ("ALPHA_STRICT_LEADER_JSON", "ALPHA_ALLOW_PROSE_LEADER_BATON")
    snap = _env_snapshot(keys)
    try:
        os.environ["ALPHA_STRICT_LEADER_JSON"] = "1"
        os.environ.pop("ALPHA_ALLOW_PROSE_LEADER_BATON", None)
        client = MagicMock()
        bad = MagicMock(choices=[MagicMock(message=MagicMock(content="not json at all"))])
        client.chat.completions.create.side_effect = [bad, bad]
        nt, st = o.call_leader(client, "model", "idea", "ragctx", "curtask")
        d = json.loads(st)
        assert nt == "curtask"
        assert d.get("parse_error") is True
        assert d.get("ledger_delta") == "leader_json_parse_failed"
        assert client.chat.completions.create.call_count == 2
        print("p7_strict_fail_ok")
    finally:
        _env_restore(snap)


def p7_strict_valid_first():
    keys = ("ALPHA_STRICT_LEADER_JSON", "ALPHA_ALLOW_PROSE_LEADER_BATON")
    snap = _env_snapshot(keys)
    try:
        os.environ["ALPHA_STRICT_LEADER_JSON"] = "1"
        os.environ.pop("ALPHA_ALLOW_PROSE_LEADER_BATON", None)
        payload = {
            "core_objective_anchor": "anchor",
            "ledger_delta": "ld",
            "highest_active_risk": "risk",
            "baton_pass": {"next_task": "  do next  "},
        }
        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(payload)))]
        )
        nt, st = o.call_leader(client, "model", "idea", "rag", "task0")
        d = json.loads(st)
        assert d["baton_pass"]["next_task"] == "do next"
        assert nt == "do next"
        assert client.chat.completions.create.call_count == 1
        ca = client.chat.completions.create.call_args
        assert ca[1]["temperature"] == 0.0
        print("p7_strict_ok_ok")
    finally:
        _env_restore(snap)


def p7_strict_prose_escape():
    keys = ("ALPHA_STRICT_LEADER_JSON", "ALPHA_ALLOW_PROSE_LEADER_BATON")
    snap = _env_snapshot(keys)
    try:
        os.environ["ALPHA_STRICT_LEADER_JSON"] = "1"
        os.environ["ALPHA_ALLOW_PROSE_LEADER_BATON"] = "1"
        client = MagicMock()
        bad = MagicMock(choices=[MagicMock(message=MagicMock(content="not json"))])
        client.chat.completions.create.side_effect = [bad, bad]
        nt, st = o.call_leader(client, "m", "ie", "r", "ct")
        d = json.loads(st)
        assert d.get("ledger_delta") == "fallback_unstructured_leader_output"
        assert nt == "not json"
        print("p7_prose_escape_ok")
    finally:
        _env_restore(snap)


def p7_loose_temperature():
    keys = ("ALPHA_STRICT_LEADER_JSON",)
    snap = _env_snapshot(keys)
    try:
        os.environ["ALPHA_STRICT_LEADER_JSON"] = "0"
        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="plain next task text"))]
        )
        o.call_leader(client, "m", "ie", "r", "ct")
        assert client.chat.completions.create.call_args[1]["temperature"] == 0.2
        print("p7_loose_temp_ok")
    finally:
        _env_restore(snap)


if __name__ == "__main__":
    p4_main_loop_order()
    p7_strict_parse_fail()
    p7_strict_valid_first()
    p7_strict_prose_escape()
    p7_loose_temperature()
    print("wave3_all_ok")
