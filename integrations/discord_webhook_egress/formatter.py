from .schemas import AlertPacket

def format_discord_message(packet: AlertPacket) -> str:
    """Formats the alert packet into a markdown string for Discord."""
    severity_upper = packet.severity.upper()
    title = f"[{severity_upper}] {packet.asset} - {packet.event_type.upper()}"
    
    lines = [
        f"**{title}**",
        "",
        f"**Session:** {packet.session}",
        f"**Timeframe:** {packet.timeframe}",
        "",
        "**Headline:**",
        packet.headline,
        "",
        "**Summary:**",
        packet.summary,
        "",
        "**Evidence:**"
    ]
    
    if packet.evidence_packets:
        for ev in packet.evidence_packets:
            lines.append(f"- {ev}")
    else:
        lines.append("- None")
        
    lines.append("")
    lines.append("**RAG / Memory References:**")
    if packet.rag_refs or packet.memory_refs:
        for ref in packet.rag_refs:
            lines.append(f"- [RAG] {ref}")
        for ref in packet.memory_refs:
            lines.append(f"- [Memory] {ref}")
    else:
        lines.append("- None")
        
    lines.extend([
        "",
        "**Confirmation Needed:**",
        packet.confirmation_needed,
        "",
        "**Invalidation:**",
        packet.invalidation,
        "",
        "**Risk Mode:**",
        packet.risk_mode,
        "",
        "**Retail Translation:**",
        packet.retail_translation,
        "",
        "**Leader Decision:**",
        packet.leader_decision,
        "",
        "**Scribe Note:**",
        packet.scribe_note,
        "",
        "---",
        "*educational scenario only, not financial advice*"
    ])
    
    return "\n".join(lines)
