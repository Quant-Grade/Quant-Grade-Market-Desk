import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from .schemas import LiquidityBandsInput

def generate_liquidity_bands_packet(input_data: LiquidityBandsInput) -> Dict[str, Any]:
    """
    Transforms LiquidityBandsInput into a valid Discord Egress AlertPacket format.
    Applies strict logic rules.
    """
    event_type = "liquidity_sweep_watch"
    severity = "watch"
    risk_mode = input_data.risk_mode
    confirmation_needed = "Confirmation is pending observation of market structure."
    
    # Rule: If sweep_status is sweeping_now, severity should be at least important
    if input_data.sweep_status == "sweeping_now":
        severity = "important"
        
    # Rule: Risk mode modifications based on reaction
    if input_data.reaction_status == "acceptance":
        risk_mode = "Warning: Level may be failing. Acceptance observed."
    elif input_data.reaction_status == "chop":
        risk_mode = "No chase. Chop risk."
        
    # Rule: Clean rejection confirmation language
    if input_data.reaction_status == "clean_rejection":
        confirmation_needed = "Clean rejection observed. Await structural shift on lower timeframe."
        
    # Rule: Fail closed on forbidden predictive/promotional language
    forbidden_phrases = ["buy here", "sell here", "guaranteed", "risk-free", "100%", "must enter", "easy money", "signal to enter now", "financial advice"]
    
    def sanitize_fail_closed(text: str) -> str:
        lower_t = text.lower()
        for phrase in forbidden_phrases:
            if phrase in lower_t:
                from .schemas import InputValidationError
                raise InputValidationError(f"Forbidden language detected in input: '{phrase}'")
        return text

    headline = f"{input_data.asset} interacting with {input_data.liquidity_type.replace('_', ' ').title()}"
    summary = f"Price: {input_data.price} | Nearest zone: {input_data.zone}. {input_data.current_behavior}"
    
    evidence = [
        f"Sweep Status: {input_data.sweep_status.replace('_', ' ').title()}",
        f"Reaction Status: {input_data.reaction_status.replace('_', ' ').title()}",
        f"Distance to Zone: {input_data.distance_to_zone_pct}%",
        sanitize_fail_closed(input_data.structure_context)
    ]
    
    packet = {
        "v": 1,
        "packet_id": f"liq_band_{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_system": "liquidity_bands_packet_producer",
        "source_role": "liquidity_bands",
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
        "confirmation_needed": sanitize_fail_closed(confirmation_needed),
        "invalidation": "Acceptance past the liquidity band voids the immediate reversal thesis.",
        "risk_mode": sanitize_fail_closed(risk_mode),
        "retail_translation": "Price is testing an area where large orders often sit. We are monitoring the reaction.",
        "leader_decision": "Packet generated for review; egress adapter must validate before send.",
        "scribe_note": "Generated autonomously by Liquidity Bands producer.",
        "not_financial_advice": True
    }
    
    return packet
