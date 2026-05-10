import json
from dataclasses import dataclass
from typing import Dict, Any

class InputValidationError(Exception):
    pass

@dataclass
class VWAPInput:
    asset: str
    timeframe: str
    session: str
    price: float
    vwap: float
    distance_to_vwap: float
    distance_to_vwap_pct: float
    prior_displacement: str
    current_behavior: str
    structure_context: str
    microstructure_confirmation: str
    risk_mode: str

def parse_vwap_input(data: Dict[str, Any]) -> VWAPInput:
    required_keys = [
        "asset", "timeframe", "session", "price", "vwap", "distance_to_vwap",
        "distance_to_vwap_pct", "prior_displacement", "current_behavior",
        "structure_context", "microstructure_confirmation", "risk_mode"
    ]
    
    for key in required_keys:
        if key not in data:
            raise InputValidationError(f"Missing required key in input: {key}")
            
    try:
        return VWAPInput(
            asset=str(data["asset"]),
            timeframe=str(data["timeframe"]),
            session=str(data["session"]),
            price=float(data["price"]),
            vwap=float(data["vwap"]),
            distance_to_vwap=float(data["distance_to_vwap"]),
            distance_to_vwap_pct=float(data["distance_to_vwap_pct"]),
            prior_displacement=str(data["prior_displacement"]),
            current_behavior=str(data["current_behavior"]),
            structure_context=str(data["structure_context"]),
            microstructure_confirmation=str(data["microstructure_confirmation"]),
            risk_mode=str(data["risk_mode"])
        )
    except Exception as e:
        raise InputValidationError(f"Type validation failed: {e}")

def load_vwap_input(filepath: str) -> VWAPInput:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_vwap_input(data)
    except json.JSONDecodeError as e:
        raise InputValidationError(f"Invalid JSON: {e}")
