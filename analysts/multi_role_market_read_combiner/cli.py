import argparse
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import load_source_packet, CombinerValidationError, InputValidationError
from .combiner import generate_multi_role_packet

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "packets"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(packet_id: str, status: str, error: str = None):
    init_dirs()
    log_file = LOGS_DIR / "multi_role_market_read_combiner.jsonl"
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
    parser = argparse.ArgumentParser(description="Multi-Role Market Read Combiner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    combine_parser = subparsers.add_parser("combine", help="Combine analyst packets")
    combine_parser.add_argument("--vwap", type=str, default=str(OUTPUTS_DIR / "latest_vwap_packet.json"), help="Path to VWAP packet")
    combine_parser.add_argument("--session", type=str, default=str(OUTPUTS_DIR / "latest_session_open_packet.json"), help="Path to Session Open packet")
    combine_parser.add_argument("--liquidity", type=str, default=str(OUTPUTS_DIR / "latest_liquidity_bands_packet.json"), help="Path to Liquidity Bands packet")

    args = parser.parse_args()

    if args.command == "combine":
        paths = {
            "vwap": Path(args.vwap),
            "session": Path(args.session),
            "liquidity": Path(args.liquidity)
        }
        
        packets = {}
        for role, path in paths.items():
            if not path.exists():
                print(f"Error: Required packet missing: {path}", file=sys.stderr)
                append_log("unknown", "failed", f"Missing packet: {path}")
                sys.exit(1)
                
            try:
                packets[role] = load_source_packet(str(path))
            except CombinerValidationError as e:
                print(f"Combiner Validation Error: {e}", file=sys.stderr)
                append_log("unknown", "failed", str(e))
                sys.exit(1)

        # Generate Combined Packet
        try:
            combined_packet = generate_multi_role_packet(
                packets["vwap"], 
                packets["session"], 
                packets["liquidity"]
            )
        except (CombinerValidationError, InputValidationError) as e:
            print(f"Combiner Error: {e}", file=sys.stderr)
            append_log("unknown", "failed", str(e))
            sys.exit(1)
        
        # Write Output
        init_dirs()
        out_file = OUTPUTS_DIR / "latest_multi_role_market_read_packet.json"
        
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(combined_packet, f, indent=2)
            print(f"Combined packet produced and written to {out_file}")
            append_log(combined_packet["packet_id"], "success")
        except Exception as e:
            print(f"Error writing combined output: {e}", file=sys.stderr)
            append_log(combined_packet["packet_id"], "failed", str(e))
            sys.exit(1)

if __name__ == "__main__":
    main()
