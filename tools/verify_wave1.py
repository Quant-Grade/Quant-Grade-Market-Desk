import json, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o

def p6_missing():
    env = {k:v for k,v in os.environ.items() if not k.startswith("ALPHA_")}
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", "import orchestrator as x; x._require_operational_limits_or_exit()"], env=env, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]))
    assert p.returncode == 2
    print("p6_missing_ok")

def p6_allow():
    env = {k:v for k,v in os.environ.items() if not k.startswith("ALPHA_")}
    env["ALPHA_ALLOW_UNBOUNDED_LOOP"] = "1"
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", "import orchestrator as x; x._require_operational_limits_or_exit(); print('ok')"], env=env, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]))
    assert p.returncode == 0 and "ok" in p.stdout
    print("p6_allow_ok")

def p2():
    td = Path(tempfile.mkdtemp())
    p = td / "a.jsonl"
    rec = {"round_id": 3, "leader_next_task": "nxt", "state_tracker": {"a": 1}, "organized_memory": "om", "builder_expansion": "b", "compressor_summary": "c", "redteam_attacks": "r"}
    p.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert o.load_last_alpha_jsonl_record(p)["round_id"] == 3
    assert len(o.rebuild_last_round_texts_from_jsonl(p, 5)) == 1
    print("p2_ok")

def p3():
    from unittest.mock import MagicMock
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content='{"idea_expansion":"a","query_memory_for":"b"}'))])
    st = '{"ledger_delta":"k","core_objective_anchor":"g","baton_pass":{"next_task":"t"}}'
    o.call_builder(client, "m", "t1", prior_state_json=st, prior_organized_memory="mem")
    u = client.chat.completions.create.call_args[1]["messages"][1]["content"]
    assert "PRIOR_STATE_TRACKER" in u and "PRIOR_ORGANIZED_MEMORY" in u
    print("p3_ok")

if __name__ == "__main__":
    p6_missing()
    p6_allow()
    p2()
    p3()
    print("wave1_all_ok")
