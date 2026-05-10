from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone

class OperatorProfile(Enum):
    DRY_RUN_LATEST = "dry_run_latest"
    SEND_IF_ALLOWED_LATEST = "send_if_allowed_latest"
    STATUS_ONLY = "status_only"
    DEBUG_LATEST = "debug_latest"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_

class OperatorResult:
    def __init__(self, run_id: str, profile_used: str, symbol: Optional[str] = None):
        self.run_id = run_id
        self.profile_used = profile_used
        self.symbol = symbol
        self.status = "RUNNING"
        self.pipeline_exit_code: Optional[int] = None
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.details: Dict[str, Any] = {}
        self.errors: list = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "profile_used": self.profile_used,
            "symbol": self.symbol,
            "status": self.status,
            "pipeline_exit_code": self.pipeline_exit_code,
            "timestamp": self.timestamp,
            "details": self.details,
            "errors": self.errors
        }

class OperatorError(Exception):
    pass
