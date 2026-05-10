import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from integrations.discord_webhook_egress.schemas import validate_packet_dict, AlertPacket
from .schemas import InputValidationError, HallucinationError
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .llm_client import query_local_llm

def write_market_report(input_packet: AlertPacket, mock_llm_response: str = None) -> Dict[str, Any]:
    """Orchestrates the rewriting of an AlertPacket via a Local LLM."""
    
    # 1. Build Payload
    input_json = json.dumps(input_packet.__dict__, indent=2)
    user_prompt = build_user_prompt(input_json)
    
    # 2. Query LLM
    if mock_llm_response is not None:
        raw_response = mock_llm_response
    else:
        raw_response = query_local_llm(SYSTEM_PROMPT, user_prompt)
        print("RAW LLM RESPONSE:", repr(raw_response))
        
    # 3. Parse JSON strict
    try:
        llm_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise InputValidationError(f"LLM returned invalid JSON: {e}")
        
    # 4. Check for Hallucinated Fields and Missing Fields
    allowed_llm_keys = {
        "headline", "summary", "evidence_packets", "retail_translation",
        "confirmation_needed", "invalidation", "risk_mode"
    }
    
    for key in llm_data.keys():
        if key not in allowed_llm_keys:
            raise HallucinationError(f"LLM hallucinated unsupported field: {key}")
            
    for req_key in allowed_llm_keys:
        if req_key not in llm_data:
            raise InputValidationError(f"LLM omitted required field: {req_key}")
            
    # 5. Build Final Packet mapped over base properties
    packet = {
        "v": 1,
        "packet_id": f"llm_rep_{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_system": "local_llm_market_report_writer",
        "source_role": "multi_role",
        "asset": input_packet.asset,
        "timeframe": input_packet.timeframe,
        "session": input_packet.session,
        "event_type": "multi_role_market_read",
        "severity": input_packet.severity,
        "headline": llm_data.get("headline", ""),
        "summary": llm_data.get("summary", ""),
        "evidence_packets": llm_data.get("evidence_packets", []),
        "rag_refs": input_packet.rag_refs,
        "memory_refs": input_packet.memory_refs,
        "confirmation_needed": llm_data.get("confirmation_needed", ""),
        "invalidation": llm_data.get("invalidation", ""),
        "risk_mode": llm_data.get("risk_mode", ""),
        "retail_translation": llm_data.get("retail_translation", ""),
        "leader_decision": "LLM report generated from deterministic packets; egress adapter must validate before send.",
        "scribe_note": f"Rewritten via Local LLM. Source packet ID: {input_packet.packet_id}",
        "not_financial_advice": True
    }
    
    # 6. Sanitize Fail Closed for Forbidden Language
    forbidden_phrases = ["buy here", "sell here", "guaranteed", "risk-free", "100%", "must enter", "easy money", "signal to enter now", "financial advice"]
    
    packet_str_check = json.dumps(packet).lower()
    for phrase in forbidden_phrases:
        if phrase in packet_str_check:
            raise InputValidationError(f"Forbidden language detected in LLM output: '{phrase}'")
            
    # 7. Final Output Validation (checks for missing fields via Egress frozen schema)
    try:
        validate_packet_dict(packet)
    except Exception as e:
        raise InputValidationError(f"LLM output failed structural validation: {e}")
        
    return packet
