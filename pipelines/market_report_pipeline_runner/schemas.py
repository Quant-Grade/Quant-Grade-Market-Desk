from typing import List, Dict, Any, Optional

class PipelineResult:
    def __init__(self, run_id: str, started_at: str, input_mode: str = "sample"):
        self.run_id = run_id
        self.started_at = started_at
        self.input_mode = input_mode
        self.snapshot_builder_ran: bool = False
        self.finished_at: str = ""
        self.steps_run: List[str] = []
        self.packet_paths: Dict[str, str] = {}
        self.generated_input_paths: Dict[str, str] = {}
        self.snapshot_input_path: Optional[str] = None
        self.resolved_snapshot_input_path: Optional[str] = None
        self.snapshot_source_type: Optional[str] = None
        self.latest_resolver_ran: bool = False
        self.snapshot_root: Optional[str] = None
        self.symbol: Optional[str] = None
        self.source: Optional[str] = None
        self.used_real_ingestion_input: bool = False
        self.policy_decision: Dict[str, Any] = {}
        self.egress_action: str = "NONE"
        self.status: str = "RUNNING"
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "input_mode": self.input_mode,
            "snapshot_builder_ran": self.snapshot_builder_ran,
            "finished_at": self.finished_at,
            "steps_run": self.steps_run,
            "packet_paths": self.packet_paths,
            "generated_input_paths": self.generated_input_paths,
            "snapshot_input_path": self.snapshot_input_path,
            "resolved_snapshot_input_path": self.resolved_snapshot_input_path,
            "snapshot_source_type": self.snapshot_source_type,
            "latest_resolver_ran": self.latest_resolver_ran,
            "snapshot_root": self.snapshot_root,
            "symbol": self.symbol,
            "source": self.source,
            "used_real_ingestion_input": self.used_real_ingestion_input,
            "policy_decision": self.policy_decision,
            "egress_action": self.egress_action,
            "status": self.status,
            "errors": self.errors
        }
