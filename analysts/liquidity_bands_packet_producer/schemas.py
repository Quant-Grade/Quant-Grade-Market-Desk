import json
from dataclasses import dataclass
from typing import Dict, Any

class InputValidationError(Exception):
    pass

ALLOWED_LIQUIDITY_TYPES = {
    "prior_session_high", "prior_session_low", "poor_high", "poor_low", 
    "untouched_upper_wick", "untouched_lower_wick", "range_high", "range_low", "manual_zone"
}

ALLOWED_SWEEP_STATUSES = {
    "not_swept", "sweeping_now", "swept_rejected", "swept_accepted", "unclear"
}

ALLOWED_REACTION_STATUSES = {
    "no_reaction", "weak_reaction", "clean_rejection", "acceptance", "chop", "unclear"
}

@dataclass
class LiquidityBandsInput:
    asset: str
    timeframe: str
    session: str
    price: float
    nearest_upper_liquidity: float
    nearest_lower_liquidity: float
    liquidity_type: str
    distance_to_zone: float
    distance_to_zone_pct: float
    zone: str
    current_behavior: str
    structure_context: str
    sweep_status: str
    reaction_status: str
    risk_mode: str

def parse_liquidity_bands_input(data: Dict[str, Any]) -> LiquidityBandsInput:
    required_keys = [
        "asset", "timeframe", "session", "price", "nearest_upper_liquidity",
        "nearest_lower_liquidity", "liquidity_type", "distance_to_zone",
        "distance_to_zone_pct", "zone", "current_behavior", "structure_context",
        "sweep_status", "reaction_status", "risk_mode"
    ]
    
    for key in required_keys:
        if key not in data:
            raise InputValidationError(f"Missing required key in input: {key}")
            
    liquidity_type = str(data["liquidity_type"])
    if liquidity_type not in ALLOWED_LIQUIDITY_TYPES:
        raise InputValidationError(f"Invalid liquidity_type: {liquidity_type}")

    sweep_status = str(data["sweep_status"])
    if sweep_status not in ALLOWED_SWEEP_STATUSES:
        raise InputValidationError(f"Invalid sweep_status: {sweep_status}")

    reaction_status = str(data["reaction_status"])
    if reaction_status not in ALLOWED_REACTION_STATUSES:
        raise InputValidationError(f"Invalid reaction_status: {reaction_status}")
        
    try:
        return LiquidityBandsInput(
            asset=str(data["asset"]),
            timeframe=str(data["timeframe"]),
            session=str(data["session"]),
            price=float(data["price"]),
            nearest_upper_liquidity=float(data["nearest_upper_liquidity"]),
            nearest_lower_liquidity=float(data["nearest_lower_liquidity"]),
            liquidity_type=liquidity_type,
            distance_to_zone=float(data["distance_to_zone"]),
            distance_to_zone_pct=float(data["distance_to_zone_pct"]),
            zone=str(data["zone"]),
            current_behavior=str(data["current_behavior"]),
            structure_context=str(data["structure_context"]),
            sweep_status=sweep_status,
            reaction_status=reaction_status,
            risk_mode=str(data["risk_mode"])
        )
    except Exception as e:
        raise InputValidationError(f"Type validation failed: {e}")

def load_liquidity_bands_input(filepath: str) -> LiquidityBandsInput:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_liquidity_bands_input(data)
    except json.JSONDecodeError as e:
        raise InputValidationError(f"Invalid JSON: {e}")
