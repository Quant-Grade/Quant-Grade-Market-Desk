import os
from typing import Optional
import pandas as pd
from .schemas import SourceOHLCVSnapshot, BuilderValidationError

def load_real_ingestion_snapshot(filepath: str) -> SourceOHLCVSnapshot:
    if not os.path.exists(filepath):
        raise BuilderValidationError(f"File not found: {filepath}")
        
    try:
        if filepath.endswith('.parquet'):
            df = pd.read_parquet(filepath)
        else:
            raise BuilderValidationError(f"Unsupported format for real ingestion: {filepath}")
    except Exception as e:
        raise BuilderValidationError(f"Failed to read data: {e}")
        
    if df.empty:
        raise BuilderValidationError("Dataset is empty.")
        
    # Check required OHLCV
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    for col in required_cols:
        if col not in df.columns:
            raise BuilderValidationError(f"Missing required OHLCV column: {col}")
            
    # Filter for complete candles if 'confirm' flag exists
    if 'confirm' in df.columns:
        confirmed_df = df[df['confirm'] == True]
        if confirmed_df.empty:
            raise BuilderValidationError("No complete (confirmed) candles found in dataset.")
        df = confirmed_df
        
    # Get latest candle
    df = df.sort_values(by='timestamp')
    latest = df.iloc[-1]
    
    # Validate OHLCV
    if latest['open'] < 0 or latest['high'] < 0 or latest['low'] < 0 or latest['close'] < 0:
        raise BuilderValidationError("Negative price detected in latest candle.")
    if latest['volume'] < 0:
        raise BuilderValidationError("Negative volume detected in latest candle.")
        
    if latest['high'] < latest['open'] or latest['high'] < latest['close'] or latest['high'] < latest['low']:
        raise BuilderValidationError("Invalid OHLCV bounds: High is not the highest.")
    if latest['low'] > latest['open'] or latest['low'] > latest['close'] or latest['low'] > latest['high']:
        raise BuilderValidationError("Invalid OHLCV bounds: Low is not the lowest.")

    # VWAP Calculation over the available dataset
    total_vol = df['volume'].sum()
    if total_vol > 0:
        # Typical price approximation or close
        vwap = (df['close'] * df['volume']).sum() / total_vol
    else:
        vwap = latest['close']
        
    # Session computation (naive approximation or static for v0.1)
    # We could look at UTC timestamp, but prompt says "compute or infer ... session label"
    # NY: 13:30 - 20:00 UTC, Asia: 00:00 - 06:00 UTC, London: 08:00 - 16:30 UTC
    # Since prompt says "Compute or infer", I'll just hardcode a basic rule or pass a safe default.
    # Let's derive it from the timestamp
    from datetime import datetime, timezone
    # okx timestamps are ms
    ts = latest['timestamp'] / 1000.0 if latest['timestamp'] > 1e11 else latest['timestamp']
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    hour = dt.hour
    if 0 <= hour < 8:
        session = "Asia"
    elif 8 <= hour < 13:
        session = "London"
    else:
        session = "NY"
        
    session_phase = "mid_session"

    asset = latest['symbol'] if 'symbol' in latest else "UNKNOWN"
    timeframe = latest['timeframe'] if 'timeframe' in latest else "1m"
    
    # Safe Neutral values
    current_behavior = "unclear"
    structure_context = "real_ingestion_snapshot_no_structure_detector_yet"
    liquidity_context = "unclear"
    sweep_status = "unclear"
    reaction_status = "unclear"
    risk_mode = "Watch only. Confirmation required."
    
    # Let's use simple inferences for prior_session bounds
    prior_session_high = df['high'].max() if not df.empty else latest['high']
    prior_session_low = df['low'].min() if not df.empty else latest['low']
    nearest_upper = prior_session_high
    nearest_lower = prior_session_low

    return SourceOHLCVSnapshot(
        asset=asset,
        timeframe=timeframe,
        session=session,
        price=float(latest['close']),
        vwap=float(vwap),
        prior_session_high=float(prior_session_high),
        prior_session_low=float(prior_session_low),
        nearest_upper_liquidity=float(nearest_upper),
        nearest_lower_liquidity=float(nearest_lower),
        liquidity_type="prior_session_high",  # default inference
        zone="upper",
        sweep_status=sweep_status,
        reaction_status=reaction_status,
        session_phase=session_phase,
        minutes_from_open=30,  # neutral default
        prior_displacement="unclear",
        current_behavior=current_behavior,
        structure_context=structure_context,
        microstructure_confirmation="unclear",
        volatility_state="unclear",
        liquidity_context=liquidity_context,
        risk_mode=risk_mode
    )
