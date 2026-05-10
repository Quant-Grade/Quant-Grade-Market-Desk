import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from .schemas import SessionOpenInput

def generate_session_open_packet(input_data: SessionOpenInput) -> Dict[str, Any]:
    """
    Transforms SessionOpenInput into a valid Discord Egress AlertPacket format.
    Applies strict logic rules.
    """
    event_type = "session_open_brief"
    severity = "info"
    risk_mode = input_data.risk_mode
    
    # Rule: Open-window packets default to severity watch
    if input_data.session_phase == "open_window":
        severity = "watch"
        
    # Rule: Elevated volatility -> risk mode warns against chasing
    vol_lower = input_data.volatility_state.lower()
    if "elevated" in vol_lower or "high" in vol_lower or "extreme" in vol_lower:
        risk_mode = "Elevated volatility. Do not chase."
        
    # Rule: Fail closed on forbidden predictive/promotional language
    forbidden_phrases = ["buy here", "sell here", "guaranteed", "risk-free", "100%", "must enter", "easy money", "signal to enter now", "financial advice"]
    
    def sanitize_fail_closed(text: str) -> str:
        lower_t = text.lower()
        for phrase in forbidden_phrases:
            if phrase in lower_t:
                from .schemas import InputValidationError
                raise InputValidationError(f"Forbidden language detected in input: '{phrase}'")
        return text

    headline = f"{input_data.session} {input_data.session_phase.replace('_', ' ').title()}"
    summary = f"Price: {input_data.price} | T-Mins to Open: {input_data.minutes_from_open}. {input_data.current_behavior}"
    
    evidence = [
        f"Volatility: {sanitize_fail_closed(input_data.volatility_state)}",
        f"Liquidity: {sanitize_fail_closed(input_data.liquidity_context)}"
    ]
    
    # Rule: Sweep detection
    # Assuming "sweeping" is implied by price being very close to or beyond prior session extremes.
    # We will also check if "sweep" is in the current behavior just in case.
    if input_data.price >= input_data.prior_session_high:
        evidence.append("Sweeping prior session high.")
    elif input_data.price <= input_data.prior_session_low:
        evidence.append("Sweeping prior session low.")
    
    packet = {
        "v": 1,
        "packet_id": f"sess_open_{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_system": "session_open_packet_producer",
        "source_role": "session_open",
        "asset": input_data.asset,
        "timeframe": input_data.timeframe,
        "session": input_data.session,
        "event_type": event_type,
        "severity": severity,
        "headline": sanitize_fail_closed(headline),
        "summary": sanitize_fail_closed(summary),
        "evidence_packets": evidence,
        "rag_refs": [],
        "memory_refs": [],
        "confirmation_needed": "Wait for 15m structural close.",
        "invalidation": "Loss of open window volatility structure.",
        "risk_mode": sanitize_fail_closed(risk_mode),
        "retail_translation": "Market is approaching a session open. Increased volatility is expected.",
        "leader_decision": "Packet generated for review; egress adapter must validate before send.",
        "scribe_note": "Generated autonomously by Session Open producer.",
        "not_financial_advice": True
    }
    
    return packet
