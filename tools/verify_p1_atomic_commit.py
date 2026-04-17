import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import orchestrator as o
td = Path(tempfile.mkdtemp())
alpha = td / "data" / "alpha_concepts.jsonl"
alpha.parent.mkdir(parents=True)
idea = td / "idea.md"
idea.write_text("# test\n", encoding="utf-8")
o._rag_v2_base = td
o.IDEA_LOG_PATH = idea
o.commit_round_checkpoint(99, "t", "ie", "q", "c", "r", "n", "{}", "om", "rag snap")
j1 = alpha.read_text(encoding="utf-8")
assert "99" in j1 and "rag snap" in j1
assert "## Round 99" in idea.read_text(encoding="utf-8")
print("commit_ok")
_path_open = Path.open


class Boom(Exception):
    pass


def path_open_patch(self, *args, **kwargs):
    mode = args[0] if args else kwargs.get("mode", "r")
    if self.resolve() == idea.resolve() and "a" in str(mode):
        raise Boom("simulated_idea_failure")
    return _path_open(self, *args, **kwargs)


Path.open = path_open_patch
try:
    o.commit_round_checkpoint(100, "t2", "ie2", "q2", "c2", "r2", "n2", "{}", "", "")
except Boom:
    pass
finally:
    Path.open = _path_open
lines = alpha.read_text(encoding="utf-8").strip().splitlines()
assert len(lines) == 1
print("rollback_ok")
