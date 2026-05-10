import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
import re

from integrations.discord_webhook_egress.schemas import AlertPacket
from .schemas import CombinerValidationError, InputValidationError

def generate_multi_role_packet(vwap_packet: AlertPacket, session_packet: AlertPacket, liq_packet: AlertPacket) -> Dict[str, Any]:
    """Combines three analyst packets into a single multi_role_market_read packet."""
    
    # 1. Validate Asset Match
    if not (vwap_packet.asset == session_packet.asset == liq_packet.asset):
        raise CombinerValidationError("Asset mismatch among source packets.")
        
    asset = vwap_packet.asset
    timeframe = vwap_packet.timeframe
    session = session_packet.session
    
    packets = [vwap_packet, session_packet, liq_packet]
    
    # 2. Determine Highest Severity
    severity_rank = {"urgent": 4, "important": 3, "watch": 2, "info": 1}
    highest_sev = "info"
    max_rank = 1
    for p in packets:
        rank = severity_rank.get(p.severity, 1)
        if rank > max_rank:
            max_rank = rank
            highest_sev = p.severity
            
    # 3. Compile Evidence
    evidence_packets = []
    evidence_packets.append(f"[VWAP] {vwap_packet.summary}")
    for ev in vwap_packet.evidence_packets:
        evidence_packets.append(f"  - {ev}")
        
    evidence_packets.append(f"[SESSION] {session_packet.summary}")
    for ev in session_packet.evidence_packets:
        evidence_packets.append(f"  - {ev}")
        
    evidence_packets.append(f"[LIQUIDITY] {liq_packet.summary}")
    for ev in liq_packet.evidence_packets:
        evidence_packets.append(f"  - {ev}")

    # 4. Risk Rules & Conflict Detection
    risk_parts = []
    
    # Check for conflict: if risk modes are wildly different or evidence is contradictory
    unique_risk_modes = set([p.risk_mode for p in packets])
    evidence_lower = " ".join([e.lower() for e in evidence_packets])
    
    is_conflict = len(unique_risk_modes) > 1 or ("rejection" in evidence_lower and "acceptance" in evidence_lower)
    
    if is_conflict:
        risk_parts.append("Mixed evidence. Watch only. Confirmation required.")
        
    if any("chop" in p.risk_mode.lower() for p in packets):
        if "No chase. Chop risk." not in risk_parts:
            risk_parts.append("No chase. Chop risk.")
            
    if any("elevated volatility" in p.risk_mode.lower() for p in packets) or "elevated volatility" in evidence_lower:
        if "Open-window volatility risk." not in risk_parts:
            risk_parts.append("Open-window volatility risk.")
            
    if not risk_parts:
        risk_parts.append("Standard execution mode.")
        
    risk_mode_final = " | ".join(risk_parts)
    
    # 5. Confirmation Rules
    confirmation_parts = []
    if vwap_packet.severity == "watch" or "none" in vwap_packet.confirmation_needed.lower() or "missing" in vwap_packet.confirmation_needed.lower():
        confirmation_parts.append("VWAP confirmation is still required.")
        
    # Add other confirmations
    for p in packets:
        if p.confirmation_needed and p.confirmation_needed not in confirmation_parts and "none" not in p.confirmation_needed.lower():
            confirmation_parts.append(p.confirmation_needed)
            
    confirmation_final = " ".join(confirmation_parts) if confirmation_parts else "Await structural shift."
    
    # 6. Sanitize Fail Closed
    forbidden_phrases = ["buy here", "sell here", "guaranteed", "risk-free", "100%", "must enter", "easy money", "signal to enter now", "financial advice"]
    
    def sanitize_fail_closed(text: str) -> str:
        lower_t = text.lower()
        for phrase in forbidden_phrases:
            if phrase in lower_t:
                raise InputValidationError(f"Forbidden language detected in combined input: '{phrase}'")
        return text
        
    # 7. Scribe Note
    packet_ids = [p.packet_id for p in packets]
    scribe_note = f"Combined packet IDs: {', '.join(packet_ids)}"

    combined_packet = {
        "v": 1,
        "packet_id": f"multi_{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_system": "multi_role_market_read_combiner",
        "source_role": "multi_role",
        "asset": asset,
        "timeframe": timeframe,
        "session": session,
        "event_type": "multi_role_market_read",
        "severity": highest_sev,
        "headline": sanitize_fail_closed(f"Multi-Role Market Read: {asset}"),
        "summary": sanitize_fail_closed("Amalgamated scenario from VWAP, Session Open, and Liquidity Bands analysts."),
        "evidence_packets": [sanitize_fail_closed(e) for e in evidence_packets],
        "rag_refs": [],
        "memory_refs": [],
        "confirmation_needed": sanitize_fail_closed(confirmation_final),
        "invalidation": "Loss of confluence across multiple timeframes.",
        "risk_mode": sanitize_fail_closed(risk_mode_final),
        "retail_translation": "We are looking at multiple indicators at once to confirm market direction safely.",
        "leader_decision": "Combined deterministic analyst packets for Discord review.",
        "scribe_note": sanitize_fail_closed(scribe_note),
        "not_financial_advice": True
    }
    
    return combined_packet
