from typing import Dict, Any
from integrations.discord_webhook_egress.schemas import parse_packet_file, validate_packet_dict, AlertPacket, SchemaValidationError

class PolicyValidationError(Exception):
    pass

def load_and_validate_packet(filepath: str) -> AlertPacket:
    try:
        return parse_packet_file(filepath)
    except (SchemaValidationError, FileNotFoundError) as e:
        raise PolicyValidationError(f"Invalid or missing packet: {e}")
