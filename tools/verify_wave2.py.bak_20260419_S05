import json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o

def p5_prepend_atomic():
    td = Path(tempfile.mkdtemp())
    idea = td / "idea_log.md"
    idea.write_text("BODY\n", encoding="utf-8")
    o.IDEA_LOG_PATH = idea
    o.prepend_state_summary(7, "bullet one")
    txt = idea.read_text(encoding="utf-8")
    assert txt.startswith("### STATE OF THE THEORY (Round 7)")
    assert "bullet one" in txt and "BODY" in txt
    assert not (td / "idea_log.md.tmp").exists()
    print("p5_prepend_ok")

def p8_rotate_lines():
    td = Path(tempfile.mkdtemp())
    p = td / "data" / "alpha_concepts.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("\n".join([json.dumps({"round": i}) for i in range(5)]) + "\n", encoding="utf-8")
    old_env = os.environ.get("ALPHA_JSONL_MAX_LINES")
    os.environ["ALPHA_JSONL_MAX_LINES"] = "3"
    try:
        o.maybe_rotate_alpha_jsonl(p)
        assert not p.exists()
        arch = list((td / "data" / "archive").glob("alpha_concepts_*.jsonl"))
        assert len(arch) == 1
        assert arch[0].stat().st_size > 0
    finally:
        if old_env is None:
            os.environ.pop("ALPHA_JSONL_MAX_LINES", None)
        else:
            os.environ["ALPHA_JSONL_MAX_LINES"] = old_env
    print("p8_rotate_ok")

def p8_no_rotate_when_under():
    td = Path(tempfile.mkdtemp())
    p = td / "data" / "alpha_concepts.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"round": 1}) + "\n", encoding="utf-8")
    old = os.environ.get("ALPHA_JSONL_MAX_LINES")
    os.environ["ALPHA_JSONL_MAX_LINES"] = "100"
    try:
        o.maybe_rotate_alpha_jsonl(p)
        assert p.exists()
    finally:
        if old is None:
            os.environ.pop("ALPHA_JSONL_MAX_LINES", None)
        else:
            os.environ["ALPHA_JSONL_MAX_LINES"] = old
    print("p8_no_rotate_ok")

if __name__ == "__main__":
    p5_prepend_atomic()
    p8_rotate_lines()
    p8_no_rotate_when_under()
    print("wave2_all_ok")
