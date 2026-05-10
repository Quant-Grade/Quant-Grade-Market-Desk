import argparse
import sys
import json
from pathlib import Path

from .runner import run_operator_profile
from .schemas import OperatorError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "ops"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(result_dict: dict):
    init_dirs()
    log_file = LOGS_DIR / "operator_run_profiles.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result_dict) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Operator Run Profiles Control Layer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    run_parser = subparsers.add_parser("run", help="Run a specific profile")
    run_parser.add_argument("--profile", type=str, required=True, help="Profile to run (e.g. dry_run_latest)")
    run_parser.add_argument("--symbol", type=str, default=None, help="Symbol to run against (e.g. BTC-USDT-SWAP)")
    
    status_parser = subparsers.add_parser("status", help="Get status of latest pipeline run without executing")
    
    args = parser.parse_args()
    
    try:
        if args.command == "run":
            result = run_operator_profile(profile_str=args.profile, symbol=args.symbol)
        elif args.command == "status":
            result = run_operator_profile(profile_str="status_only")
            
        res_dict = result.to_dict()
        
        init_dirs()
        out_file = OUTPUTS_DIR / "latest_operator_run.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(res_dict, f, indent=2)
            
        append_log(res_dict)
        
        if result.status == "SUCCESS":
            if args.command == "status":
                print(json.dumps(res_dict, indent=2))
            else:
                print(f"Operator profile {res_dict['profile_used']} completed successfully.")
            sys.exit(0)
        else:
            print(f"Operator profile failed: {res_dict['errors']}", file=sys.stderr)
            sys.exit(1)
            
    except OperatorError as e:
        print(f"Operator Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
