"""
Read-only diagnostic for Alpha Engine STATE_TRACKER output.

Scans idea_log.md for per-round State Tracker JSON blocks and prints
a compact table:
round | core_objective_anchor | highest_active_risk | baton_pass.next_task | status
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "idea_log.md"


def iter_round_blocks(text: str):
    """Yield (round_number, block_text) for each '## Round N' section."""
    pattern = re.compile(r"^## Round\s+(\d+)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        round_num = int(m.group(1))
        yield round_num, text[start:end]


def extract_state_tracker(block: str) -> tuple[str, str, str, str]:
    """
    Extract (status, core_anchor, highest_risk, baton_next) from a single round block.

    Status is:
      - 'ok' if JSON parsed and fields present
      - 'missing' if no State Tracker section
      - 'invalid' if JSON present but failed to parse
    """
    marker = "### State Tracker"
    idx = block.find(marker)
    if idx == -1:
        return "missing", "", "", ""

    after = block[idx + len(marker) :]
    # Take lines until the next '## ' (new round) or end
    lines = []
    for line in after.splitlines():
        if line.startswith("## "):
            break
        # Skip the marker's own blank and heading line
        if not lines and not line.strip():
            continue
        lines.append(line)

    raw = "\n".join(lines).strip()
    if not raw:
        return "invalid", "", "", ""

    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return "invalid", "", "", ""
        core = str(data.get("core_objective_anchor", "") or "")
        risk = str(data.get("highest_active_risk", "") or "")
        baton = data.get("baton_pass") or {}
        baton_next = str(baton.get("next_task", "") or "")
        return "ok", core, risk, baton_next
    except Exception:
        return "invalid", "", "", ""


def main() -> None:
    if not LOG_PATH.exists():
        print(f"idea_log.md not found at {LOG_PATH}")
        return

    text = LOG_PATH.read_text(encoding="utf-8")
    print("round | status   | core_objective_anchor | highest_active_risk | baton_next_task")
    print("----- | -------- | ---------------------- | -------------------- | ---------------")

    for round_num, block in iter_round_blocks(text):
        status, core, risk, baton = extract_state_tracker(block)
        # Compact, single-line, truncated view
        core_s = (core[:40] + "…") if len(core) > 40 else core
        risk_s = (risk[:40] + "…") if len(risk) > 40 else risk
        baton_s = (baton[:40] + "…") if len(baton) > 40 else baton
        print(f"{round_num:5d} | {status:8s} | {core_s} | {risk_s} | {baton_s}")


if __name__ == "__main__":
    main()

