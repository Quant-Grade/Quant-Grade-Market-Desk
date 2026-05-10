import argparse
import sys
import json
from pathlib import Path

from .runner import execute_pipeline

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs" / "pipeline"
LOGS_DIR = REPO_ROOT / "logs"

def init_dirs():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def append_log(result_dict: dict):
    init_dirs()
    log_file = LOGS_DIR / "market_report_pipeline_runner.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result_dict) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Market Report Pipeline Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full deterministic pipeline")
    run_parser.add_argument("--send", action="store_true", help="Attempt to send to Discord live via Egress")
    run_parser.add_argument("--dry-run", action="store_true", help="Dry run only (default behavior)")
    run_parser.add_argument("--skip-llm", action="store_true", help="Skip the LLM generation step")
    run_parser.add_argument("--input-mode", type=str, default="sample", help="Input mode for producers (default: sample)")

    run_parser.add_argument("--snapshot-input", type=str, default=None, help="Path to real ingestion parquet data")
    run_parser.add_argument("--snapshot-root", type=str, default=r"C:\CryptoSystems\Collector - OKX\data\normalized\okx\candles", help="Root directory for latest parquet resolver")
    run_parser.add_argument("--source", type=str, default="okx_ws", help="Source filter for latest parquet resolver")
    run_parser.add_argument("--symbol", type=str, default=None, help="Symbol filter for latest parquet resolver")

    args = parser.parse_args()

    if args.command == "run":
        send_flag = args.send
        dry_run_flag = args.dry_run
        
        # Default is dry-run. If send is passed, it overrides dry-run (but send must be explicitly true).
        # We pass `send` to execute_pipeline.
        print("Starting Market Report Pipeline...")
        
        pipeline_result = execute_pipeline(
            send=send_flag,
            dry_run=not send_flag, # if not sending, it's dry-run conceptually
            skip_llm=args.skip_llm,
            input_mode=args.input_mode,
            snapshot_input=args.snapshot_input,
            snapshot_root=args.snapshot_root,
            source=args.source,
            symbol=args.symbol
        )
        
        res_dict = pipeline_result.to_dict()
        
        init_dirs()
        out_file = OUTPUTS_DIR / "latest_pipeline_result.json"
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(res_dict, f, indent=2)
            append_log(res_dict)
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            sys.exit(1)
            
        print(f"\nPipeline Finished. Status: {pipeline_result.status}")
        print(f"Steps run: {', '.join(pipeline_result.steps_run)}")
        print(f"Egress Action: {pipeline_result.egress_action}")
        
        if pipeline_result.status == "FAILED":
            print("\nErrors encountered:")
            for err in pipeline_result.errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        else:
            sys.exit(0)

if __name__ == "__main__":
    main()
