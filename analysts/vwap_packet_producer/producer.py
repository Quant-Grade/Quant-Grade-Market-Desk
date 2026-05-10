import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from .schemas import VWAPInput

def generate_vwap_packet(input_data: VWAPInput) -> Dict[str, Any]:
    """
    Transforms VWAPInput into a valid Discord Egress AlertPacket format.
    Applies strict logic rules.
    """
    # Base extraction
    event_type = "vwap_watch"  # Default for VWAP packets
    severity = "info"
    risk_mode = input_data.risk_mode
    
    behavior_lower = input_data.current_behavior.lower()
    conf_lower = input_data.microstructure_confirmation.lower()
    
    # Rule: If chopping around VWAP, override risk mode
    if "chop" in behavior_lower:
        risk_mode = "No chase. Chop risk."
        
    # Rule: If near VWAP and confirmation is missing
    # Let's consider 'near' as implicit if we are analyzing a VWAP interaction, 
    # but we can explicitly check if "near" is in behavior or distance is small.
    # The prompt says: "If price is near VWAP and confirmation is missing"
    is_missing_conf = ("none" in conf_lower or "missing" in conf_lower or not conf_lower)
    # We will assume if this producer is invoked, price is near VWAP, or check distance < 0.5%
    if abs(input_data.distance_to_vwap_pct) < 1.0 and is_missing_conf:
        event_type = "vwap_watch"
        severity = "watch"
        
    # Build headline and summary safely without forbidden language
    headline = f"{input_data.asset} interacting with VWAP"
    summary = f"Price: {input_data.price} | VWAP: {input_data.vwap}. {input_data.current_behavior}"
    
    # Ensure no forbidden language leaks in from input
    forbidden_phrases = ["buy here", "sell here", "guaranteed", "risk-free", "100%", "must enter", "easy money", "signal to enter now", "financial advice"]
    
    def sanitize(text: str) -> str:
        lower_t = text.lower()
        for phrase in forbidden_phrases:
            if phrase in lower_t:
                from .schemas import InputValidationError
                raise InputValidationError(f"Forbidden language detected in input: '{phrase}'")
        return text

    evidence = [
        f"Distance to VWAP: {input_data.distance_to_vwap_pct}%",
        sanitize(input_data.prior_displacement),
        sanitize(input_data.structure_context)
    ]
    
    packet = {
        "v": 1,
        "packet_id": f"vwap_prod_{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_system": "vwap_packet_producer",
        "source_role": "vwap",
        "asset": input_data.asset,
        "timeframe": input_data.timeframe,
        "session": input_data.session,
        "event_type": event_type,
        "severity": severity,
        "headline": sanitize(headline),
        "summary": sanitize(summary),
        "evidence_packets": evidence,
        "rag_refs": [],
        "memory_refs": [],
        "confirmation_needed": sanitize(input_data.microstructure_confirmation),
        "invalidation": "Loss of structural context or adverse volume absorption.",
        "risk_mode": sanitize(risk_mode),
        "retail_translation": "Price is near the daily volume-weighted average. The signal is how it reacts, not a certain bounce.",
        "leader_decision": "Packet generated for review; egress adapter must validate before send.",
        "scribe_note": "Generated autonomously by VWAP producer.",
        "not_financial_advice": True
    }
    
    return packet
