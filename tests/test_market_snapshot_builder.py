import unittest
import json
import os
from pathlib import Path

from context.market_snapshot_builder.schemas import parse_source_snapshot, BuilderValidationError
from context.market_snapshot_builder.builder import build_vwap_input, build_session_open_input, build_liquidity_bands_input

class TestMarketSnapshotBuilder(unittest.TestCase):

    def setUp(self):
        self.sample_data = {
            "asset": "BTC",
            "timeframe": "1m",
            "session": "NY",
            "price": 64500.50,
            "vwap": 64300.00,
            "prior_session_high": 64800.00,
            "prior_session_low": 63900.00,
            "nearest_upper_liquidity": 64850.00,
            "nearest_lower_liquidity": 64100.00,
            "liquidity_type": "prior_session_high",
            "zone": "upper",
            "sweep_status": "sweeping_now",
            "reaction_status": "no_reaction",
            "session_phase": "open_window",
            "minutes_from_open": 15,
            "prior_displacement": "bullish",
            "current_behavior": "aggressive_expansion",
            "structure_context": "testing_resistance",
            "microstructure_confirmation": "heavy_buy_volume",
            "volatility_state": "expanding",
            "liquidity_context": "thin_orderbook",
            "risk_mode": "Normal"
        }
        self.snapshot = parse_source_snapshot(self.sample_data)

    def test_sample_builds_all_three_inputs(self):
        # We test that all builders return a valid dict
        vwap = build_vwap_input(self.snapshot)
        session = build_session_open_input(self.snapshot)
        liq = build_liquidity_bands_input(self.snapshot)
        
        self.assertIn("distance_to_vwap", vwap)
        self.assertIn("session_phase", session)
        self.assertIn("distance_to_zone", liq)

    def test_generated_vwap_passes_schema(self):
        from analysts.vwap_packet_producer.schemas import parse_vwap_input
        vwap_dict = build_vwap_input(self.snapshot)
        parsed = parse_vwap_input(vwap_dict)
        self.assertEqual(parsed.price, 64500.5)

    def test_generated_session_passes_schema(self):
        from analysts.session_open_packet_producer.schemas import parse_session_open_input
        session_dict = build_session_open_input(self.snapshot)
        parsed = parse_session_open_input(session_dict)
        self.assertEqual(parsed.session_phase, "open_window")

    def test_generated_liquidity_passes_schema(self):
        from analysts.liquidity_bands_packet_producer.schemas import parse_liquidity_bands_input
        liq_dict = build_liquidity_bands_input(self.snapshot)
        parsed = parse_liquidity_bands_input(liq_dict)
        self.assertEqual(parsed.liquidity_type, "prior_session_high")

    def test_invalid_ohlcv_fails_closed(self):
        # Try missing a qualitative state
        invalid_data = self.sample_data.copy()
        del invalid_data["volatility_state"]
        with self.assertRaises(BuilderValidationError):
            parse_source_snapshot(invalid_data)

    def test_missing_price_fails_closed(self):
        invalid_data = self.sample_data.copy()
        del invalid_data["price"]
        with self.assertRaises(BuilderValidationError):
            parse_source_snapshot(invalid_data)

if __name__ == '__main__':
    unittest.main()
