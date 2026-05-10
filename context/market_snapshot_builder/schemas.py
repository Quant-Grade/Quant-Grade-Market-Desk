import json
from dataclasses import dataclass
from typing import Dict, Any

class BuilderValidationError(Exception):
    pass

@dataclass
class SourceOHLCVSnapshot:
    asset: str
    timeframe: str
    session: str
    price: float
    vwap: float
    # Calculated / Pass-through states
    prior_session_high: float
    prior_session_low: float
    nearest_upper_liquidity: float
    nearest_lower_liquidity: float
    liquidity_type: str
    zone: str
    sweep_status: str
    reaction_status: str
    session_phase: str
    minutes_from_open: int
    prior_displacement: str
    current_behavior: str
    structure_context: str
    microstructure_confirmation: str
    volatility_state: str
    liquidity_context: str
    risk_mode: str

def parse_source_snapshot(data: Dict[str, Any]) -> SourceOHLCVSnapshot:
    required_keys = [
        "asset", "timeframe", "session", "price", "vwap", "prior_session_high",
        "prior_session_low", "nearest_upper_liquidity", "nearest_lower_liquidity",
        "liquidity_type", "zone", "sweep_status", "reaction_status", "session_phase",
        "minutes_from_open", "prior_displacement", "current_behavior", "structure_context",
        "microstructure_confirmation", "volatility_state", "liquidity_context", "risk_mode"
    ]
    
    for key in required_keys:
        if key not in data:
            raise BuilderValidationError(f"Missing required key in snapshot: {key}")
            
    try:
        return SourceOHLCVSnapshot(
            asset=str(data["asset"]),
            timeframe=str(data["timeframe"]),
            session=str(data["session"]),
            price=float(data["price"]),
            vwap=float(data["vwap"]),
            prior_session_high=float(data["prior_session_high"]),
            prior_session_low=float(data["prior_session_low"]),
            nearest_upper_liquidity=float(data["nearest_upper_liquidity"]),
            nearest_lower_liquidity=float(data["nearest_lower_liquidity"]),
            liquidity_type=str(data["liquidity_type"]),
            zone=str(data["zone"]),
            sweep_status=str(data["sweep_status"]),
            reaction_status=str(data["reaction_status"]),
            session_phase=str(data["session_phase"]),
            minutes_from_open=int(data["minutes_from_open"]),
            prior_displacement=str(data["prior_displacement"]),
            current_behavior=str(data["current_behavior"]),
            structure_context=str(data["structure_context"]),
            microstructure_confirmation=str(data["microstructure_confirmation"]),
            volatility_state=str(data["volatility_state"]),
            liquidity_context=str(data["liquidity_context"]),
            risk_mode=str(data["risk_mode"])
        )
    except Exception as e:
        raise BuilderValidationError(f"Type validation failed: {e}")
