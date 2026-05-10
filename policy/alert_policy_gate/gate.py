import time
from typing import Dict, Any

from integrations.discord_webhook_egress.schemas import validate_packet_dict, AlertPacket
from .schemas import PolicyValidationError
from .storage import is_duplicate, get_last_event_time

COOLDOWN_SECONDS = 3600 # 1 hour cooldown by default

def evaluate_packet(packet: AlertPacket) -> Dict[str, Any]:
    """Evaluates an AlertPacket against the deterministic policy rules."""
    
    decision = {
        "status": "UNKNOWN",
        "reason": "",
        "packet_id": packet.packet_id
    }
    
    # 1. Structural Safety Check (Block Unsafe)
    try:
        validate_packet_dict(packet.__dict__)
    except Exception as e:
        decision["status"] = "BLOCK_UNSAFE"
        decision["reason"] = f"Packet structurally unsafe: {e}"
        return decision
        
    # 2. Duplicate Check
    if is_duplicate(packet.packet_id):
        decision["status"] = "BLOCK_DUPLICATE"
        decision["reason"] = "Packet ID has already been sent."
        return decision
        
    # 3. Severity Logic
    if packet.severity == "info":
        decision["status"] = "BLOCK_LOW_SEVERITY"
        decision["reason"] = "Info severity is blocked by default."
        return decision
        
    if packet.severity == "watch":
        decision["status"] = "DOWNGRADE_DRY_RUN_ONLY"
        decision["reason"] = "Watch severity is downgraded to dry-run only."
        return decision
        
    # 4. Cooldown Check (Only applies to important/urgent or anything making it this far)
    # Actually, prompt says "Allow urgent unless unsafe." which implies urgent bypasses cooldown!
    # Let's enforce cooldown ONLY for 'important'
    if packet.severity != "urgent":
        last_time = get_last_event_time(packet.asset, packet.event_type)
        now = time.time()
        if now - last_time < COOLDOWN_SECONDS:
            decision["status"] = "BLOCK_COOLDOWN"
            decision["reason"] = f"Cooldown active for {packet.asset} {packet.event_type}."
            return decision

    # 5. Allow Send
    decision["status"] = "ALLOW_SEND"
    decision["reason"] = "Packet meets all policy requirements."
    return decision
