import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

ALLOWED_SOURCE_ROLES = {
    "leader", "scribe", "builder", "vwap", "twap", "cvd", "rvol", "bbo",
    "microstructure", "liquidity_bands", "session_open", "news", "sentiment",
    "token_unlocks", "multi_role"
}

ALLOWED_EVENT_TYPES = {
    "vwap_watch", "twap_pathing_watch", "cvd_divergence_watch",
    "rvol_expansion_watch", "bbo_pressure_watch", "liquidity_sweep_watch",
    "microstructure_shift", "session_open_brief", "news_risk_brief",
    "sentiment_shift", "token_unlock_watch", "multi_role_market_read",
    "no_trade_warning"
}

ALLOWED_SEVERITIES = {
    "info", "watch", "important", "urgent"
}

class SchemaValidationError(Exception):
    pass

@dataclass
class AlertPacket:
    v: int
    packet_id: str
    created_at: str
    source_system: str
    source_role: str
    asset: str
    timeframe: str
    session: str
    event_type: str
    severity: str
    headline: str
    summary: str
    evidence_packets: List[str]
    rag_refs: List[str]
    memory_refs: List[str]
    confirmation_needed: str
    invalidation: str
    risk_mode: str
    retail_translation: str
    leader_decision: str
    scribe_note: str
    not_financial_advice: bool

def validate_packet_dict(data: Dict[str, Any]) -> AlertPacket:
    if not data:
        raise SchemaValidationError("Empty packet")

    # Enforce envelope discipline: "v": 1 must be the first key
    first_key = list(data.keys())[0]
    if first_key != "v":
        raise SchemaValidationError(f"Invalid envelope: first key must be 'v', got '{first_key}'")
    
    if data["v"] != 1 or not isinstance(data["v"], int):  # Strict type and value check
        raise SchemaValidationError(f"Invalid envelope version: expected integer 1, got {data['v']} ({type(data['v'])})")

    if data.get("source_role") not in ALLOWED_SOURCE_ROLES:
        raise SchemaValidationError(f"Invalid source_role: {data.get('source_role')}")
    
    if data.get("event_type") not in ALLOWED_EVENT_TYPES:
        raise SchemaValidationError(f"Invalid event_type: {data.get('event_type')}")
    
    if data.get("severity") not in ALLOWED_SEVERITIES:
        raise SchemaValidationError(f"Invalid severity: {data.get('severity')}")

    required_keys = [
        "v", "packet_id", "created_at", "source_system", "source_role",
        "asset", "timeframe", "session", "event_type", "severity",
        "headline", "summary", "evidence_packets", "rag_refs", "memory_refs",
        "confirmation_needed", "invalidation", "risk_mode", "retail_translation",
        "leader_decision", "scribe_note", "not_financial_advice"
    ]

    for key in required_keys:
        if key not in data:
            raise SchemaValidationError(f"Missing required key: {key}")

    try:
        return AlertPacket(
            v=data["v"],
            packet_id=data["packet_id"],
            created_at=data["created_at"],
            source_system=data["source_system"],
            source_role=data["source_role"],
            asset=data["asset"],
            timeframe=data["timeframe"],
            session=data["session"],
            event_type=data["event_type"],
            severity=data["severity"],
            headline=data["headline"],
            summary=data["summary"],
            evidence_packets=data["evidence_packets"],
            rag_refs=data["rag_refs"],
            memory_refs=data["memory_refs"],
            confirmation_needed=data["confirmation_needed"],
            invalidation=data["invalidation"],
            risk_mode=data["risk_mode"],
            retail_translation=data["retail_translation"],
            leader_decision=data["leader_decision"],
            scribe_note=data["scribe_note"],
            not_financial_advice=data["not_financial_advice"]
        )
    except Exception as e:
        raise SchemaValidationError(f"Type validation failed: {str(e)}")

def parse_packet_file(filepath: str) -> AlertPacket:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            # json.load preserves order in Python 3.7+
            data = json.load(f)
        return validate_packet_dict(data)
    except json.JSONDecodeError as e:
        raise SchemaValidationError(f"Invalid JSON: {str(e)}")
