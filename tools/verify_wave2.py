import json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o

def p5_prepend_atomic():
    """P5 (Round-85 contract): prepend_state_summary appends a YAML-frontmatter
    block to THEORY_LOG_PATH (theory_log.md). Append-only: idea_log.md is not
    modified, no .tmp scratch file is created, subsequent calls append rather
    than replace, and empty summaries are a no-op.
    """
    td = Path(tempfile.mkdtemp())
    idea = td / "idea_log.md"
    theory = td / "theory_log.md"
    idea.write_text("BODY\n", encoding="utf-8")
    idea_before = idea.read_bytes()
    o.IDEA_LOG_PATH = idea
    o.THEORY_LOG_PATH = theory

    # Call 1: round 7 -> round_range 3-7 (lo = max(1, 7-4) = 3, hi = 7)
    o.prepend_state_summary(7, "bullet one")
    assert theory.exists(), "theory_log.md not created by prepend_state_summary"
    txt1 = theory.read_text(encoding="utf-8")
    assert "theory_log_version: 1" in txt1, "missing theory_log_version in frontmatter"
    assert "round_range: 3-7" in txt1, "wrong round_range for round 7"
    assert "bullet one" in txt1, "summary content not written"
    assert idea.read_bytes() == idea_before, "idea_log.md modified by prepend_state_summary"
    assert not (td / "idea_log.md.tmp").exists(), "stale idea_log.md.tmp scratch file created"
    assert not (td / "theory_log.md.tmp").exists(), "unexpected theory_log.md.tmp scratch file"

    # Call 2: append-only (second call must not replace first)
    o.prepend_state_summary(12, "bullet two")
    txt2 = theory.read_text(encoding="utf-8")
    assert txt2.startswith(txt1), "theory_log.md is not append-only"
    assert "round_range: 8-12" in txt2, "wrong round_range for round 12"
    assert "bullet two" in txt2, "second summary not appended"
    assert "bullet one" in txt2, "first summary dropped on second call"
    assert txt2.count("theory_log_version: 1") == 2, "expected exactly two frontmatter blocks"

    # Call 3: empty summary is a no-op
    before_empty = theory.read_text(encoding="utf-8")
    o.prepend_state_summary(15, "")
    after_empty = theory.read_text(encoding="utf-8")
    assert after_empty == before_empty, "empty summary should be a no-op"

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
