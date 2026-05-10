import json
from dataclasses import dataclass
from typing import Dict, Any

class InputValidationError(Exception):
    pass

@dataclass
class SessionOpenInput:
    asset: str
    timeframe: str
    session: str
    session_phase: str
    minutes_from_open: int
    price: float
    vwap: float
    prior_session_high: float
    prior_session_low: float
    current_behavior: str
    volatility_state: str
    liquidity_context: str
    risk_mode: str

def parse_session_open_input(data: Dict[str, Any]) -> SessionOpenInput:
    required_keys = [
        "asset", "timeframe", "session", "session_phase", "minutes_from_open",
        "price", "vwap", "prior_session_high", "prior_session_low",
        "current_behavior", "volatility_state", "liquidity_context", "risk_mode"
    ]
    
    for key in required_keys:
        if key not in data:
            raise InputValidationError(f"Missing required key in input: {key}")
            
    session = str(data["session"])
    if session not in ["Asia", "London", "NY"]:
        raise InputValidationError(f"Invalid session: {session}. Must be Asia, London, or NY.")
        
    session_phase = str(data["session_phase"])
    if session_phase not in ["pre_open", "open_window", "post_open", "mid_session"]:
        raise InputValidationError(f"Invalid session_phase: {session_phase}. Must be pre_open, open_window, post_open, or mid_session.")
        
    try:
        return SessionOpenInput(
            asset=str(data["asset"]),
            timeframe=str(data["timeframe"]),
            session=session,
            session_phase=session_phase,
            minutes_from_open=int(data["minutes_from_open"]),
            price=float(data["price"]),
            vwap=float(data["vwap"]),
            prior_session_high=float(data["prior_session_high"]),
            prior_session_low=float(data["prior_session_low"]),
            current_behavior=str(data["current_behavior"]),
            volatility_state=str(data["volatility_state"]),
            liquidity_context=str(data["liquidity_context"]),
            risk_mode=str(data["risk_mode"])
        )
    except Exception as e:
        raise InputValidationError(f"Type validation failed: {e}")

def load_session_open_input(filepath: str) -> SessionOpenInput:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_session_open_input(data)
    except json.JSONDecodeError as e:
        raise InputValidationError(f"Invalid JSON: {e}")
