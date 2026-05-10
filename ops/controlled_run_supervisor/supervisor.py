import time
import uuid
from typing import Optional
from datetime import datetime, timezone

from ops.operator_run_profiles.runner import run_operator_profile
from .schemas import SupervisorResult, SupervisorError

def run_supervisor(
    profile: str,
    max_runs: int,
    symbol: Optional[str] = None,
    interval_seconds: int = 300,
    continue_on_error: bool = False
) -> SupervisorResult:
    
    if max_runs is None or max_runs <= 0:
        raise SupervisorError("max_runs must be specified and greater than zero.")
        
    result = SupervisorResult(
        run_id=f"sup_{uuid.uuid4().hex[:8]}",
        profile=profile,
        symbol=symbol,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        continue_on_error=continue_on_error
    )
    
    try:
        for i in range(max_runs):
            # Run the operator layer natively (in same process but decoupled)
            op_result = run_operator_profile(profile_str=profile, symbol=symbol)
            op_dict = op_result.to_dict()
            
            result.run_history.append(op_dict)
            result.runs_completed += 1
            
            if op_result.status != "SUCCESS":
                if not continue_on_error:
                    result.status = "FAILED"
                    result.errors.append(f"Operator Run {i+1} failed and continue_on_error is False.")
                    break
                else:
                    result.errors.append(f"Operator Run {i+1} failed, but continuing due to continue_on_error.")
            
            # Sleep if not the last run
            if i < max_runs - 1:
                time.sleep(interval_seconds)
                
        if result.status != "FAILED":
            result.status = "SUCCESS"
            
    except Exception as e:
        result.status = "FAILED"
        result.errors.append(f"Unexpected supervisor failure: {e}")
        
    result.finished_at = datetime.now(timezone.utc).isoformat()
    return result
