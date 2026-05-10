import json
from .schemas import SourceOHLCVSnapshot, parse_source_snapshot, BuilderValidationError

def load_snapshot_file(filepath: str) -> SourceOHLCVSnapshot:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_source_snapshot(data)
    except FileNotFoundError:
        raise BuilderValidationError(f"File not found: {filepath}")
    except json.JSONDecodeError as e:
        raise BuilderValidationError(f"Invalid JSON in {filepath}: {e}")
