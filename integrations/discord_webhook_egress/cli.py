import argparse
import os
import sys
from pathlib import Path

from .schemas import parse_packet_file, SchemaValidationError
from .formatter import format_discord_message
from .safety import check_safety, SafetyViolationError, check_length, MessageTooLongError
from .client import send_to_discord
from .storage import append_log, write_latest_message

def main():
    parser = argparse.ArgumentParser(description="Discord Webhook Egress Adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run_parser = subparsers.add_parser("dry-run", help="Render message without sending")
    dry_run_parser.add_argument("--sample", type=str, help="Name of the sample packet to use")
    dry_run_parser.add_argument("--file", type=str, help="Path to the JSON packet file")

    send_parser = subparsers.add_parser("send", help="Render and send message to Discord")
    send_parser.add_argument("--sample", type=str, help="Name of the sample packet to use")
    send_parser.add_argument("--file", type=str, help="Path to the JSON packet file")

    args = parser.parse_args()

    if not args.sample and not args.file:
        print("Error: Must provide either --sample or --file", file=sys.stderr)
        sys.exit(1)
        
    if args.sample and args.file:
        print("Error: Cannot provide both --sample and --file", file=sys.stderr)
        sys.exit(1)

    if args.sample:
        # Resolve sample path
        base_dir = Path(__file__).resolve().parent
        file_path = base_dir / "sample_packets" / f"{args.sample}.json"
    else:
        file_path = Path(args.file)

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Parse & Validate Schema
    try:
        packet = parse_packet_file(str(file_path))
    except SchemaValidationError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Format Message
    rendered_output = format_discord_message(packet)
    
    # Write latest to outputs
    write_latest_message(rendered_output)

    # 3. Safety Check
    try:
        check_safety(rendered_output)
    except SafetyViolationError as e:
        print(f"Safety Guard Blocked Sending: {e}", file=sys.stderr)
        append_log(packet.packet_id, args.command, "blocked", str(e))
        sys.exit(1)

    # 4. Length Check
    length_warning = ""
    try:
        check_length(rendered_output)
    except MessageTooLongError as e:
        if args.command == "send":
            print(f"Error: {e}", file=sys.stderr)
            append_log(packet.packet_id, args.command, "blocked", str(e))
            sys.exit(1)
        else:
            length_warning = f"\nWARNING: {e}\n"

    if args.command == "dry-run":
        print(f"--- Dry Run Successful ---\n{rendered_output}\n--------------------------{length_warning}")
        append_log(packet.packet_id, "dry-run", "success")
    elif args.command == "send":
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            error_msg = "DISCORD_WEBHOOK_URL environment variable missing"
            print(f"Error: {error_msg}", file=sys.stderr)
            append_log(packet.packet_id, "send", "failed", error_msg)
            sys.exit(1)

        try:
            send_to_discord(webhook_url, rendered_output)
            print("Message sent successfully.")
            append_log(packet.packet_id, "send", "success")
        except Exception as e:
            print(f"Error sending message: {e}", file=sys.stderr)
            append_log(packet.packet_id, "send", "failed", str(e))
            sys.exit(1)

if __name__ == "__main__":
    main()
