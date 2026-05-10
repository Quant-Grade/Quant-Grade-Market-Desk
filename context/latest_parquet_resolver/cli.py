import argparse
import sys
import json
from pathlib import Path

from .resolver import resolve_latest_parquet
from .schemas import ResolverError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "context"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(result_dict: dict):
    init_dirs()
    log_file = LOGS_DIR / "latest_parquet_resolver.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result_dict) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Latest Parquet Resolver")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    resolve_parser = subparsers.add_parser("resolve", help="Resolve the latest valid parquet file path")
    resolve_parser.add_argument("--root", type=str, required=True, help="Root directory to scan for parquet files")
    resolve_parser.add_argument("--symbol", type=str, default=None, help="Filter by symbol")
    resolve_parser.add_argument("--source", type=str, default=None, help="Filter by source")
    
    args = parser.parse_args()
    
    if args.command == "resolve":
        try:
            resolution = resolve_latest_parquet(
                root_dir=args.root,
                symbol_filter=args.symbol,
                source_filter=args.source
            )
            
            res_dict = resolution.to_dict()
            
            init_dirs()
            out_file = OUTPUTS_DIR / "latest_parquet_resolution.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(res_dict, f, indent=2)
                
            append_log(res_dict)
            
            print(f"Resolution SUCCESS. Resolved path: {resolution.resolved_path}")
            sys.exit(0)
            
        except ResolverError as e:
            print(f"Resolution FAILED: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
