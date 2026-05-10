import json
import os
import datetime
from pathlib import Path
from typing import Dict, Any

# Resolve from the root of the repository assuming this file is in integrations/discord_webhook_egress/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = REPO_ROOT / "logs"
OUTPUTS_DIR = REPO_ROOT / "outputs"

def init_directories():
    """Ensure logs and outputs directories exist."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(packet_id: str, action: str, status: str, error: str = None) -> None:
    """Appends a send attempt to logs/discord_webhook_egress.jsonl."""
    init_directories()
    log_file = LOGS_DIR / "discord_webhook_egress.jsonl"
    
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "packet_id": packet_id,
        "action": action,
        "status": status,
    }
    if error:
        record["error"] = error
        
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def write_latest_message(content: str) -> None:
    """Writes the latest rendered markdown to outputs/latest_discord_webhook_message.md."""
    init_directories()
    out_file = OUTPUTS_DIR / "latest_discord_webhook_message.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)
