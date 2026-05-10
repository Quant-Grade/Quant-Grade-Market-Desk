import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = REPO_ROOT / "logs" / "alert_policy_state.json"

def _init_state():
    if not STATE_FILE.parent.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"sent_packet_ids": [], "cooldown_ledger": {}}, f)

def load_state() -> dict:
    _init_state()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sent_packet_ids": [], "cooldown_ledger": {}}

def save_state(state: dict):
    _init_state()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def is_duplicate(packet_id: str) -> bool:
    state = load_state()
    return packet_id in state.get("sent_packet_ids", [])

def get_last_event_time(asset: str, event_type: str) -> float:
    state = load_state()
    key = f"{asset}_{event_type}"
    iso_time_str = state.get("cooldown_ledger", {}).get(key)
    if not iso_time_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso_time_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0

def record_approval(packet_id: str, asset: str, event_type: str):
    state = load_state()
    
    if "sent_packet_ids" not in state:
        state["sent_packet_ids"] = []
    if packet_id not in state["sent_packet_ids"]:
        state["sent_packet_ids"].append(packet_id)
        
    # keep only last 1000 to prevent runaway memory
    if len(state["sent_packet_ids"]) > 1000:
        state["sent_packet_ids"] = state["sent_packet_ids"][-1000:]
        
    if "cooldown_ledger" not in state:
        state["cooldown_ledger"] = {}
        
    key = f"{asset}_{event_type}"
    state["cooldown_ledger"][key] = datetime.now(timezone.utc).isoformat()
    
    save_state(state)
