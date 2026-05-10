import argparse
import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import load_vwap_input, InputValidationError
from .producer import generate_vwap_packet

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "packets"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(packet_id: str, status: str, error: str = None):
    init_dirs()
    log_file = LOGS_DIR / "vwap_packet_producer.jsonl"
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
    parser = argparse.ArgumentParser(description="VWAP Packet Producer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    produce_parser = subparsers.add_parser("produce", help="Produce an egress packet from input")
    produce_parser.add_argument("--sample", type=str, help="Name of sample input to use")
    produce_parser.add_argument("--file", type=str, help="Path to input JSON file")

    args = parser.parse_args()

    if args.command == "produce":
        if not args.sample and not args.file:
            print("Error: Must provide either --sample or --file", file=sys.stderr)
            sys.exit(1)
            
        if args.sample and args.file:
            print("Error: Cannot provide both --sample and --file", file=sys.stderr)
            sys.exit(1)

        if args.sample:
            base_dir = Path(__file__).resolve().parent
            file_path = base_dir / "sample_inputs" / f"{args.sample}.json"
        else:
            file_path = Path(args.file)

        if not file_path.exists():
            print(f"Error: Input file not found: {file_path}", file=sys.stderr)
            sys.exit(1)

        try:
            input_data = load_vwap_input(str(file_path))
        except InputValidationError as e:
            print(f"Input Validation Error: {e}", file=sys.stderr)
            append_log("unknown", "failed", str(e))
            sys.exit(1)

        # Generate Packet
        packet = generate_vwap_packet(input_data)
        
        # Write Output
        init_dirs()
        out_file = OUTPUTS_DIR / "latest_vwap_packet.json"
        
        # Write "v": 1 precisely first for dict serialization by using dict logic
        # json.dumps keeps insertion order in modern python. The producer created it with "v": 1 first.
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(packet, f, indent=2)
            print(f"Packet produced and written to {out_file}")
            append_log(packet["packet_id"], "success")
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            append_log(packet["packet_id"], "failed", str(e))
            sys.exit(1)

if __name__ == "__main__":
    main()
