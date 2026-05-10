import argparse
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import load_source_packet, InputValidationError, HallucinationError
from .writer import write_market_report

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "packets"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(packet_id: str, status: str, error: str = None):
    init_dirs()
    log_file = LOGS_DIR / "local_llm_market_report_writer.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "packet_id": packet_id,
        "status": status
    }
    if error:
        record["error"] = error
        
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Local LLM Market Report Writer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="Write a retail market report using Local LLM")
    write_parser.add_argument("--input", type=str, default=str(OUTPUTS_DIR / "latest_multi_role_market_read_packet.json"), help="Path to input packet")

    args = parser.parse_args()

    if args.command == "write":
        input_path = Path(args.input)
        
        if not input_path.exists():
            print(f"Error: Required input packet missing: {input_path}", file=sys.stderr)
            append_log("unknown", "failed", f"Missing packet: {input_path}")
            sys.exit(1)
            
        try:
            source_packet = load_source_packet(str(input_path))
        except InputValidationError as e:
            print(f"Input Validation Error: {e}", file=sys.stderr)
            append_log("unknown", "failed", str(e))
            sys.exit(1)

        # Generate LLM Packet
        try:
            print("Querying Local LLM...")
            llm_packet = write_market_report(source_packet)
        except (InputValidationError, HallucinationError, Exception) as e:
            print(f"Writer Error: {e}", file=sys.stderr)
            append_log("unknown", "failed", str(e))
            sys.exit(1)
        
        # Write Output
        init_dirs()
        out_file = OUTPUTS_DIR / "latest_llm_market_report_packet.json"
        
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(llm_packet, f, indent=2)
            print(f"LLM Market Report produced and written to {out_file}")
            append_log(llm_packet["packet_id"], "success")
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            append_log(llm_packet["packet_id"], "failed", str(e))
            sys.exit(1)

if __name__ == "__main__":
    main()
