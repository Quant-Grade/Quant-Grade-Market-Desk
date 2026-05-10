import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any

def send_to_discord(webhook_url: str, content: str) -> None:
    """
    Sends the formatted content to the Discord webhook URL.
    Fails safely if URL is missing or invalid.
    Never logs or prints the webhook URL.
    """
    if not webhook_url:
        raise ValueError("Webhook URL is missing.")

    payload = {
        "content": content
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "Ravebear-Egress-Adapter/1.0"
    })

    try:
        with urllib.request.urlopen(req) as response:
            if response.status not in (200, 204):
                raise Exception(f"Discord API returned status {response.status}")
    except urllib.error.URLError as e:
        error_msg = str(e).replace(webhook_url, "<REDACTED_URL>")
        raise Exception(f"Failed to send to Discord: {error_msg}")
