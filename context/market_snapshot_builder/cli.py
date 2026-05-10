import argparse
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from .loaders import load_snapshot_file
from .builder import build_all
from .schemas import BuilderValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "context"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(record: dict):
    init_dirs()
    log_file = LOGS_DIR / "market_snapshot_builder.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Market Snapshot Builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build context snapshots for analyst producers")
    build_parser.add_argument("--sample", action="store_true", help="Use default sample fixture")
    build_parser.add_argument("--input", type=str, help="Path to input OHLCV fixture JSON")

    args = parser.parse_args()

    if args.command == "build":
        if args.sample:
            input_path = str(Path(__file__).parent / "sample_data" / "sample_ohlcv_1m.json")
        elif args.input:
            input_path = args.input
        else:
            print("Error: Must provide --sample or --input", file=sys.stderr)
            sys.exit(1)
            
        try:
            if input_path.endswith(".parquet"):
                from .ingestion_loader import load_real_ingestion_snapshot
                snapshot = load_real_ingestion_snapshot(input_path)
            else:
                snapshot = load_snapshot_file(input_path)
                
            paths = build_all(snapshot)
            
            # Write final context snapshot mapping
            init_dirs()
            context_output = OUTPUTS_DIR / "latest_market_snapshot.json"
            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "SUCCESS",
                "source_file": input_path,
                "generated_inputs": paths
            }
            with open(context_output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
                
            append_log(result)
            print(f"Snapshot building SUCCESS. Generated inputs at: {paths}")
            sys.exit(0)
            
        except BuilderValidationError as e:
            print(f"Builder Validation Error: {e}", file=sys.stderr)
            append_log({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "FAILED",
                "source_file": input_path,
                "error": str(e)
            })
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected Error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
