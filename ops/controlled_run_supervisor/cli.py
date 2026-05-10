import argparse
import sys
import json
from pathlib import Path

from .supervisor import run_supervisor
from .schemas import SupervisorError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "ops"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(result_dict: dict):
    init_dirs()
    log_file = LOGS_DIR / "controlled_run_supervisor.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result_dict) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Controlled Run Supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    run_parser = subparsers.add_parser("run", help="Run the supervisor daemon in the foreground")
    run_parser.add_argument("--profile", type=str, default="dry_run_latest", help="Operator profile to execute (default: dry_run_latest)")
    run_parser.add_argument("--symbol", type=str, default=None, help="Symbol to run against")
    run_parser.add_argument("--interval-seconds", type=int, default=300, help="Wait time between runs (default: 300)")
    run_parser.add_argument("--max-runs", type=int, required=True, help="Maximum number of executions (required)")
    run_parser.add_argument("--continue-on-error", action="store_true", help="Continue executing if a run fails")
    
    args = parser.parse_args()
    
    if args.command == "run":
        try:
            result = run_supervisor(
                profile=args.profile,
                symbol=args.symbol,
                interval_seconds=args.interval_seconds,
                max_runs=args.max_runs,
                continue_on_error=args.continue_on_error
            )
            
            res_dict = result.to_dict()
            
            init_dirs()
            out_file = OUTPUTS_DIR / "latest_supervisor_run.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(res_dict, f, indent=2)
                
            append_log(res_dict)
            
            if result.status == "SUCCESS":
                print(f"Supervisor finished successfully after {result.runs_completed} runs.")
                sys.exit(0)
            else:
                print(f"Supervisor finished with FAILED status: {result.errors}", file=sys.stderr)
                sys.exit(1)
                
        except SupervisorError as e:
            print(f"Supervisor Configuration Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
