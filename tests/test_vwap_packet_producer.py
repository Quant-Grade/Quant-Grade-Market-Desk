import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from analysts.vwap_packet_producer.schemas import parse_vwap_input, InputValidationError
from analysts.vwap_packet_producer.producer import generate_vwap_packet

# Importing the egress schema validator to test integration
from integrations.discord_webhook_egress.schemas import validate_packet_dict

class TestVWAPPacketProducer(unittest.TestCase):

    def setUp(self):
        self.valid_input = {
            "asset": "BTC",
            "timeframe": "1m",
            "session": "NY",
            "price": 63450.50,
            "vwap": 63445.00,
            "distance_to_vwap": 5.50,
            "distance_to_vwap_pct": 0.008,
            "prior_displacement": "Strong downside displacement earlier.", 
            "current_behavior": "Price is currently interacting directly with VWAP. Slight chop developing.",
            "structure_context": "Approaching structural support from the 15m view.",
            "microstructure_confirmation": "None. Volume delta is neutral.",
            "risk_mode": "Standard execution mode."
        }

    def test_sample_input_produces_valid_packet(self):
        input_data = parse_vwap_input(self.valid_input)
        packet = generate_vwap_packet(input_data)
        
        self.assertEqual(packet["v"], 1)
        self.assertEqual(packet["source_system"], "vwap_packet_producer")
        self.assertEqual(packet["source_role"], "vwap")

    def test_packet_passes_egress_schema_validation(self):
        input_data = parse_vwap_input(self.valid_input)
        packet = generate_vwap_packet(input_data)
        
        try:
            validate_packet_dict(packet)
        except Exception as e:
            self.fail(f"Packet failed egress schema validation: {e}")

    def test_risk_mode_overridden_on_chop(self):
        # The input has "chop developing"
        input_data = parse_vwap_input(self.valid_input)
        packet = generate_vwap_packet(input_data)
        self.assertEqual(packet["risk_mode"], "No chase. Chop risk.")

    def test_event_type_watch_on_missing_confirmation(self):
        # The input has missing confirmation ("None") and is near VWAP
        input_data = parse_vwap_input(self.valid_input)
        packet = generate_vwap_packet(input_data)
        self.assertEqual(packet["event_type"], "vwap_watch")
        self.assertEqual(packet["severity"], "watch")

    def test_forbidden_language_fails_closed(self):
        # Inject forbidden language
        bad_input = self.valid_input.copy()
        bad_input["prior_displacement"] = "Strong downside displacement. It is 100% risk-free."
        
        input_data = parse_vwap_input(bad_input)
        with self.assertRaisesRegex(InputValidationError, "Forbidden language detected"):
            generate_vwap_packet(input_data)

    @patch('analysts.vwap_packet_producer.cli.OUTPUTS_DIR')
    @patch('analysts.vwap_packet_producer.cli.LOGS_DIR')
    def test_cli_outputs_are_written(self, mock_logs_dir, mock_outputs_dir):
        from analysts.vwap_packet_producer.cli import main
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_outputs_dir.return_value = tmp_path
            mock_outputs_dir.__truediv__.return_value = tmp_path / "latest_vwap_packet.json"
            mock_outputs_dir.mkdir = MagicMock()
            
            mock_logs_dir.return_value = tmp_path
            mock_logs_dir.__truediv__.return_value = tmp_path / "vwap_packet_producer.jsonl"
            mock_logs_dir.mkdir = MagicMock()

            # Create a sample input file in temp dir
            sample_path = tmp_path / "test_input.json"
            with open(sample_path, "w") as f:
                json.dump(self.valid_input, f)

            with patch.object(sys, 'argv', ['cli', 'produce', '--file', str(sample_path)]):
                main()

            out_file = tmp_path / "latest_vwap_packet.json"
            self.assertTrue(out_file.exists())
            
            log_file = tmp_path / "vwap_packet_producer.jsonl"
            self.assertTrue(log_file.exists())

if __name__ == '__main__':
    unittest.main()
