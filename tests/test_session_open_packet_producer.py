import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from analysts.session_open_packet_producer.schemas import parse_session_open_input, InputValidationError
from analysts.session_open_packet_producer.producer import generate_session_open_packet
from integrations.discord_webhook_egress.schemas import validate_packet_dict

class TestSessionOpenPacketProducer(unittest.TestCase):

    def setUp(self):
        self.valid_input = {
            "asset": "BTC",
            "timeframe": "1m",
            "session": "London",
            "session_phase": "pre_open",
            "minutes_from_open": 15,
            "price": 63500.00,
            "vwap": 63450.00,
            "prior_session_high": 64000.00,
            "prior_session_low": 63000.00,
            "current_behavior": "Consolidating near VWAP.",
            "volatility_state": "Normal volatility.",
            "liquidity_context": "Thick orderbook on both sides.",
            "risk_mode": "Standard execution mode."
        }

    def test_sample_input_produces_valid_packet(self):
        input_data = parse_session_open_input(self.valid_input)
        packet = generate_session_open_packet(input_data)
        
        self.assertEqual(packet["v"], 1)
        self.assertEqual(packet["source_system"], "session_open_packet_producer")
        self.assertEqual(packet["source_role"], "session_open")

    def test_packet_passes_egress_schema_validation(self):
        input_data = parse_session_open_input(self.valid_input)
        packet = generate_session_open_packet(input_data)
        try:
            validate_packet_dict(packet)
        except Exception as e:
            self.fail(f"Packet failed egress schema validation: {e}")

    def test_open_window_severity(self):
        data = self.valid_input.copy()
        data["session_phase"] = "open_window"
        input_data = parse_session_open_input(data)
        packet = generate_session_open_packet(input_data)
        
        self.assertEqual(packet["severity"], "watch")

    def test_volatility_risk_override(self):
        data = self.valid_input.copy()
        data["volatility_state"] = "Elevated volatility."
        input_data = parse_session_open_input(data)
        packet = generate_session_open_packet(input_data)
        
        self.assertEqual(packet["risk_mode"], "Elevated volatility. Do not chase.")

    def test_sweep_high_injection(self):
        data = self.valid_input.copy()
        data["price"] = 64005.00 # above prior high of 64000
        input_data = parse_session_open_input(data)
        packet = generate_session_open_packet(input_data)
        
        sweep_found = any("Sweeping prior session high." in ev for ev in packet["evidence_packets"])
        self.assertTrue(sweep_found)

    def test_sweep_low_injection(self):
        data = self.valid_input.copy()
        data["price"] = 62995.00 # below prior low of 63000
        input_data = parse_session_open_input(data)
        packet = generate_session_open_packet(input_data)
        
        sweep_found = any("Sweeping prior session low." in ev for ev in packet["evidence_packets"])
        self.assertTrue(sweep_found)

    def test_forbidden_language_fails_closed(self):
        bad_input = self.valid_input.copy()
        bad_input["current_behavior"] = "You must enter a long here, it's easy money."
        
        input_data = parse_session_open_input(bad_input)
        with self.assertRaisesRegex(InputValidationError, "Forbidden language detected"):
            generate_session_open_packet(input_data)

    @patch('analysts.session_open_packet_producer.cli.OUTPUTS_DIR')
    @patch('analysts.session_open_packet_producer.cli.LOGS_DIR')
    def test_cli_outputs_are_written(self, mock_logs_dir, mock_outputs_dir):
        from analysts.session_open_packet_producer.cli import main
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_outputs_dir.return_value = tmp_path
            mock_outputs_dir.__truediv__.return_value = tmp_path / "latest_session_open_packet.json"
            mock_outputs_dir.mkdir = MagicMock()
            
            mock_logs_dir.return_value = tmp_path
            mock_logs_dir.__truediv__.return_value = tmp_path / "session_open_packet_producer.jsonl"
            mock_logs_dir.mkdir = MagicMock()

            sample_path = tmp_path / "test_input.json"
            with open(sample_path, "w") as f:
                json.dump(self.valid_input, f)

            with patch.object(sys, 'argv', ['cli', 'produce', '--file', str(sample_path)]):
                main()

            out_file = tmp_path / "latest_session_open_packet.json"
            self.assertTrue(out_file.exists())
            
            log_file = tmp_path / "session_open_packet_producer.jsonl"
            self.assertTrue(log_file.exists())

if __name__ == '__main__':
    unittest.main()
