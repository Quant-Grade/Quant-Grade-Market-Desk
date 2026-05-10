from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

class SupervisorResult:
    def __init__(self, run_id: str, profile: str, symbol: Optional[str], interval_seconds: int, max_runs: int, continue_on_error: bool):
        self.run_id = run_id
        self.profile = profile
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self.max_runs = max_runs
        self.continue_on_error = continue_on_error
        self.runs_completed = 0
        self.run_history: List[Dict[str, Any]] = []
        self.status = "RUNNING"
        self.errors: List[str] = []
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "profile": self.profile,
            "symbol": self.symbol,
            "interval_seconds": self.interval_seconds,
            "max_runs": self.max_runs,
            "continue_on_error": self.continue_on_error,
            "runs_completed": self.runs_completed,
            "run_history": self.run_history,
            "status": self.status,
            "errors": self.errors,
            "started_at": self.started_at,
            "finished_at": self.finished_at
        }

class SupervisorError(Exception):
    pass
