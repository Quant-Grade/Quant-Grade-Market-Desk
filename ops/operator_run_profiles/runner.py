import subprocess
import json
import uuid
from pathlib import Path
from typing import Optional

from .schemas import OperatorProfile, OperatorResult, OperatorError
from .profiles import validate_profile

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_OUTPUTS = REPO_ROOT / "outputs" / "pipeline" / "latest_pipeline_result.json"
POLICY_OUTPUTS = REPO_ROOT / "outputs" / "policy" / "latest_alert_policy_decision.json"
RESOLVER_OUTPUTS = REPO_ROOT / "outputs" / "context" / "latest_parquet_resolution.json"

def _run_subprocess(cmd: list) -> int:
    try:
        proc = subprocess.run(cmd, check=False, cwd=str(REPO_ROOT))
        return proc.returncode
    except Exception as e:
        raise OperatorError(f"Failed to run subprocess: {e}")

def run_operator_profile(profile_str: str, symbol: Optional[str] = None) -> OperatorResult:
    profile = validate_profile(profile_str)
    
    result = OperatorResult(
        run_id=f"ops_{uuid.uuid4().hex[:8]}",
        profile_used=profile.value,
        symbol=symbol
    )
    
    if profile == OperatorProfile.STATUS_ONLY:
        # Read the latest states without running anything
        result.details["status_only"] = True
        try:
            if PIPELINE_OUTPUTS.exists():
                with open(PIPELINE_OUTPUTS, "r", encoding="utf-8") as f:
                    result.details["latest_pipeline_result"] = json.load(f)
            else:
                result.details["latest_pipeline_result"] = None
                
            if POLICY_OUTPUTS.exists():
                with open(POLICY_OUTPUTS, "r", encoding="utf-8") as f:
                    result.details["latest_policy_decision"] = json.load(f)
            else:
                result.details["latest_policy_decision"] = None

            if RESOLVER_OUTPUTS.exists():
                with open(RESOLVER_OUTPUTS, "r", encoding="utf-8") as f:
                    result.details["latest_parquet_resolution"] = json.load(f)
            else:
                result.details["latest_parquet_resolution"] = None

            result.status = "SUCCESS"
        except Exception as e:
            result.errors.append(str(e))
            result.status = "FAILED"
            
        return result

    # Build base command for active profiles
    cmd = ["python", "-m", "pipelines.market_report_pipeline_runner.cli", "run", "--input-mode", "latest"]
    if symbol:
        cmd.extend(["--symbol", symbol])

    # Map profile to exact flags
    if profile == OperatorProfile.DRY_RUN_LATEST:
        cmd.append("--dry-run")
        
    elif profile == OperatorProfile.SEND_IF_ALLOWED_LATEST:
        cmd.append("--send")
        
    elif profile == OperatorProfile.DEBUG_LATEST:
        cmd.append("--dry-run")
        # In the future, we could add a --debug flag to the pipeline runner.
        # For now, it just does a dry-run. 
        # (The requirement says "prints step trace" but Pipeline Runner already prints steps if not piped.)

    exit_code = _run_subprocess(cmd)
    result.pipeline_exit_code = exit_code
    
    if exit_code == 0:
        result.status = "SUCCESS"
    else:
        result.status = "FAILED"
        result.errors.append(f"Pipeline runner exited with code {exit_code}")

    return result
