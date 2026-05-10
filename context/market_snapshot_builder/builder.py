import json
import os
from pathlib import Path
from typing import Dict, Any

from .schemas import SourceOHLCVSnapshot, BuilderValidationError

# Import producer validators to ensure we only build compliant JSON
from analysts.vwap_packet_producer.schemas import parse_vwap_input
from analysts.session_open_packet_producer.schemas import parse_session_open_input
from analysts.liquidity_bands_packet_producer.schemas import parse_liquidity_bands_input

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATED_DIR = REPO_ROOT / "inputs" / "generated"

def init_generated_dir():
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

def build_vwap_input(source: SourceOHLCVSnapshot) -> Dict[str, Any]:
    distance_to_vwap = source.price - source.vwap
    distance_to_vwap_pct = (distance_to_vwap / source.vwap) * 100 if source.vwap > 0 else 0.0
    
    data = {
        "asset": source.asset,
        "timeframe": source.timeframe,
        "session": source.session,
        "price": source.price,
        "vwap": source.vwap,
        "distance_to_vwap": distance_to_vwap,
        "distance_to_vwap_pct": distance_to_vwap_pct,
        "prior_displacement": source.prior_displacement,
        "current_behavior": source.current_behavior,
        "structure_context": source.structure_context,
        "microstructure_confirmation": source.microstructure_confirmation,
        "risk_mode": source.risk_mode
    }
    
    # Validate against frozen producer logic
    try:
        parse_vwap_input(data)
    except Exception as e:
        raise BuilderValidationError(f"Failed to build valid VWAP input: {e}")
        
    return data

def build_session_open_input(source: SourceOHLCVSnapshot) -> Dict[str, Any]:
    data = {
        "asset": source.asset,
        "timeframe": source.timeframe,
        "session": source.session,
        "session_phase": source.session_phase,
        "minutes_from_open": source.minutes_from_open,
        "price": source.price,
        "vwap": source.vwap,
        "prior_session_high": source.prior_session_high,
        "prior_session_low": source.prior_session_low,
        "current_behavior": source.current_behavior,
        "volatility_state": source.volatility_state,
        "liquidity_context": source.liquidity_context,
        "risk_mode": source.risk_mode
    }
    
    # Validate
    try:
        parse_session_open_input(data)
    except Exception as e:
        raise BuilderValidationError(f"Failed to build valid Session Open input: {e}")
        
    return data

def build_liquidity_bands_input(source: SourceOHLCVSnapshot) -> Dict[str, Any]:
    
    # For simplicity, calculate distance to nearest liquidity based on closest zone
    dist_up = source.nearest_upper_liquidity - source.price
    dist_down = source.price - source.nearest_lower_liquidity
    
    if dist_up < dist_down:
        distance_to_zone = dist_up
        zone = "upper"
    else:
        distance_to_zone = -dist_down
        zone = "lower"
        
    distance_to_zone_pct = (distance_to_zone / source.price) * 100 if source.price > 0 else 0.0

    data = {
        "asset": source.asset,
        "timeframe": source.timeframe,
        "session": source.session,
        "price": source.price,
        "nearest_upper_liquidity": source.nearest_upper_liquidity,
        "nearest_lower_liquidity": source.nearest_lower_liquidity,
        "liquidity_type": source.liquidity_type,
        "distance_to_zone": distance_to_zone,
        "distance_to_zone_pct": distance_to_zone_pct,
        "zone": zone,
        "current_behavior": source.current_behavior,
        "structure_context": source.structure_context,
        "sweep_status": source.sweep_status,
        "reaction_status": source.reaction_status,
        "risk_mode": source.risk_mode
    }
    
    # Validate
    try:
        parse_liquidity_bands_input(data)
    except Exception as e:
        raise BuilderValidationError(f"Failed to build valid Liquidity Bands input: {e}")
        
    return data

def build_all(source: SourceOHLCVSnapshot) -> Dict[str, str]:
    init_generated_dir()
    
    vwap_data = build_vwap_input(source)
    session_data = build_session_open_input(source)
    liquidity_data = build_liquidity_bands_input(source)
    
    paths = {
        "vwap": str(GENERATED_DIR / "latest_vwap_input.json"),
        "session_open": str(GENERATED_DIR / "latest_session_open_input.json"),
        "liquidity_bands": str(GENERATED_DIR / "latest_liquidity_bands_input.json")
    }
    
    with open(paths["vwap"], "w", encoding="utf-8") as f:
        json.dump(vwap_data, f, indent=2)
        
    with open(paths["session_open"], "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2)
        
    with open(paths["liquidity_bands"], "w", encoding="utf-8") as f:
        json.dump(liquidity_data, f, indent=2)
        
    return paths
