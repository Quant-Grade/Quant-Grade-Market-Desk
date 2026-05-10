from integrations.discord_webhook_egress.schemas import parse_packet_file, AlertPacket, SchemaValidationError

class CombinerValidationError(Exception):
    pass

class InputValidationError(Exception):
    pass

def load_source_packet(filepath: str) -> AlertPacket:
    """Loads and validates a source packet against the frozen egress schema."""
    try:
        return parse_packet_file(filepath)
    except (SchemaValidationError, FileNotFoundError) as e:
        raise CombinerValidationError(f"Failed to load source packet {filepath}: {e}")
