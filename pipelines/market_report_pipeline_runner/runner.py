import subprocess
import sys
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schemas import PipelineResult

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "pipeline"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

def run_step(cmd: list, step_name: str, result: PipelineResult) -> bool:
    """Runs a subprocess command and records it in the pipeline result."""
    result.steps_run.append(step_name)
    try:
        proc = subprocess.run(cmd, check=True, cwd=str(REPO_ROOT), capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        error_msg = f"{step_name} failed with exit code {e.returncode}. Stderr: {e.stderr}"
        result.errors.append(error_msg)
        result.status = "FAILED"
        return False

def execute_pipeline(send: bool = False, dry_run: bool = True, skip_llm: bool = False, input_mode: str = "sample", snapshot_input: Optional[str] = None, snapshot_root: Optional[str] = None, source: Optional[str] = None, symbol: Optional[str] = None) -> PipelineResult:
    result = PipelineResult(
        run_id=f"run_{uuid.uuid4().hex[:8]}", 
        started_at=datetime.now(timezone.utc).isoformat(),
        input_mode=input_mode
    )
    
    # -1. Run Latest Parquet Resolver if in latest mode
    if input_mode == "latest":
        result.snapshot_root = snapshot_root
        result.source = source
        result.symbol = symbol
        
        cmd = ["python", "-m", "context.latest_parquet_resolver.cli", "resolve", "--root", snapshot_root or r"C:\CryptoSystems\Collector - OKX\data\normalized\okx\candles"]
        if symbol:
            cmd.extend(["--symbol", symbol])
        if source:
            cmd.extend(["--source", source])
            
        if not run_step(cmd, "latest_parquet_resolver", result):
            return _finish(result)
            
        result.latest_resolver_ran = True
        
        # Read the resolved path
        try:
            res_path = REPO_ROOT / "outputs" / "context" / "latest_parquet_resolution.json"
            with open(res_path, "r", encoding="utf-8") as f:
                resolution = json.load(f)
                snapshot_input = resolution.get("resolved_path")
                result.resolved_snapshot_input_path = snapshot_input
        except Exception as e:
            result.errors.append(f"Failed to read resolved parquet path: {e}")
            result.status = "FAILED"
            return _finish(result)

    # 0. Run Market Snapshot Builder if in generated or latest mode
    if input_mode in ["generated", "latest"]:
        cmd = ["python", "-m", "context.market_snapshot_builder.cli", "build"]
        if snapshot_input:
            cmd.extend(["--input", snapshot_input])
            result.snapshot_input_path = snapshot_input
            result.snapshot_source_type = "parquet" if snapshot_input.endswith(".parquet") else "json"
            result.used_real_ingestion_input = True
        else:
            cmd.append("--sample")
            
        if not run_step(cmd, "market_snapshot_builder", result):
            return _finish(result)
        result.snapshot_builder_ran = True
        
        # We know the fixed output paths of the builder
        vwap_input_path = str(REPO_ROOT / "inputs" / "generated" / "latest_vwap_input.json")
        session_input_path = str(REPO_ROOT / "inputs" / "generated" / "latest_session_open_input.json")
        liquidity_input_path = str(REPO_ROOT / "inputs" / "generated" / "latest_liquidity_bands_input.json")
        
        result.generated_input_paths = {
            "vwap": vwap_input_path,
            "session_open": session_input_path,
            "liquidity_bands": liquidity_input_path
        }

    # 1. VWAP
    cmd = ["python", "-m", "analysts.vwap_packet_producer.cli", "produce"]
    if input_mode == "sample":
        cmd.extend(["--sample", "vwap_input"])
    elif input_mode in ["generated", "latest"]:
        cmd.extend(["--file", vwap_input_path])
        
    if not run_step(cmd, "vwap_packet_producer", result):
        return _finish(result)

    # 2. Session Open
    cmd = ["python", "-m", "analysts.session_open_packet_producer.cli", "produce"]
    if input_mode == "sample":
        cmd.extend(["--sample", "session_open_input"])
    elif input_mode in ["generated", "latest"]:
        cmd.extend(["--file", session_input_path])
        
    if not run_step(cmd, "session_open_packet_producer", result):
        return _finish(result)

    # 3. Liquidity Bands
    cmd = ["python", "-m", "analysts.liquidity_bands_packet_producer.cli", "produce"]
    if input_mode == "sample":
        cmd.extend(["--sample", "liquidity_bands_input"])
    elif input_mode in ["generated", "latest"]:
        cmd.extend(["--file", liquidity_input_path])
        
    if not run_step(cmd, "liquidity_bands_packet_producer", result):
        return _finish(result)

    # 4. Combiner
    cmd = ["python", "-m", "analysts.multi_role_market_read_combiner.cli", "combine"]
    if not run_step(cmd, "multi_role_market_read_combiner", result):
        return _finish(result)

    target_packet_name = "latest_multi_role_market_read_packet.json"
    
    # 5. Local LLM Writer
    if not skip_llm:
        cmd = ["python", "-m", "analysts.local_llm_market_report_writer.cli", "write"]
        if not run_step(cmd, "local_llm_market_report_writer", result):
            return _finish(result)
        target_packet_name = "latest_llm_market_report_packet.json"
        
    packet_path = REPO_ROOT / "outputs" / "packets" / target_packet_name
    result.packet_paths["target_packet"] = str(packet_path)

    # 6. Policy Gate
    cmd = ["python", "-m", "policy.alert_policy_gate.cli", "evaluate", "--file", str(packet_path)]
    if not run_step(cmd, "alert_policy_gate", result):
        return _finish(result)
        
    # Read Policy Decision
    policy_path = REPO_ROOT / "outputs" / "policy" / "latest_alert_policy_decision.json"
    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            decision = json.load(f)
            result.policy_decision = decision
    except Exception as e:
        result.errors.append(f"Failed to read policy decision: {e}")
        result.status = "FAILED"
        return _finish(result)

    # 7. Egress logic
    status = decision.get("status", "UNKNOWN")
    
    if status == "ALLOW_SEND":
        if send:
            cmd = ["python", "-m", "integrations.discord_webhook_egress.cli", "send", "--file", str(packet_path)]
            if run_step(cmd, "discord_webhook_egress_send", result):
                result.egress_action = "SENT"
        else:
            print("SEND_ALLOWED_BUT_DRY_RUN_MODE")
            cmd = ["python", "-m", "integrations.discord_webhook_egress.cli", "dry-run", "--file", str(packet_path)]
            if run_step(cmd, "discord_webhook_egress_dry_run", result):
                result.egress_action = "DRY_RUN"
                
    elif status == "DOWNGRADE_DRY_RUN_ONLY":
        cmd = ["python", "-m", "integrations.discord_webhook_egress.cli", "dry-run", "--file", str(packet_path)]
        if run_step(cmd, "discord_webhook_egress_dry_run", result):
            result.egress_action = "DRY_RUN"
            
    elif status.startswith("BLOCK_"):
        result.egress_action = "BLOCKED"
        result.steps_run.append("egress_skipped_due_to_block")
    else:
        result.errors.append(f"Unknown policy status: {status}")
        result.status = "FAILED"
        return _finish(result)

    if result.status != "FAILED":
        result.status = "SUCCESS"
        
    return _finish(result)

def _finish(result: PipelineResult) -> PipelineResult:
    result.finished_at = datetime.now(timezone.utc).isoformat()
    return result
