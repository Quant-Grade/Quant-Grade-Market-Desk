import argparse
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import load_and_validate_packet, PolicyValidationError
from .gate import evaluate_packet
from .storage import record_approval

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "policy"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(decision: dict):
    init_dirs()
    log_file = LOGS_DIR / "alert_policy_gate.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "packet_id": decision["packet_id"],
        "status": decision["status"],
        "reason": decision["reason"]
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Alert Policy Gate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a packet for egress eligibility")
    eval_parser.add_argument("--file", type=str, default=str(REPO_ROOT / "outputs" / "packets" / "latest_llm_market_report_packet.json"), help="Path to input packet")

    args = parser.parse_args()

    if args.command == "evaluate":
        input_path = Path(args.file)
        
        if not input_path.exists():
            print(f"Error: Required input packet missing: {input_path}", file=sys.stderr)
            append_log({"packet_id": "unknown", "status": "BLOCK_UNSAFE", "reason": f"Missing file: {input_path}"})
            sys.exit(1)
            
        try:
            packet = load_and_validate_packet(str(input_path))
        except PolicyValidationError as e:
            decision = {"packet_id": "unknown", "status": "BLOCK_UNSAFE", "reason": str(e)}
            print(f"Policy Validation Error: {e}", file=sys.stderr)
            append_log(decision)
            # Write error decision to output as well
            init_dirs()
            with open(OUTPUTS_DIR / "latest_alert_policy_decision.json", "w", encoding="utf-8") as f:
                json.dump(decision, f, indent=2)
            sys.exit(1)

        # Evaluate
        decision = evaluate_packet(packet)
        print(f"Policy Decision: {decision['status']} - {decision['reason']}")
        
        # If ALLOW_SEND, record in storage so it triggers duplicate/cooldowns next time
        if decision["status"] == "ALLOW_SEND":
            record_approval(packet.packet_id, packet.asset, packet.event_type)
            
        # Write Output
        init_dirs()
        out_file = OUTPUTS_DIR / "latest_alert_policy_decision.json"
        
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(decision, f, indent=2)
            append_log(decision)
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
