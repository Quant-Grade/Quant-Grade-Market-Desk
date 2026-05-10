import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from analysts.liquidity_bands_packet_producer.schemas import parse_liquidity_bands_input, InputValidationError
from analysts.liquidity_bands_packet_producer.producer import generate_liquidity_bands_packet
from integrations.discord_webhook_egress.schemas import validate_packet_dict

class TestLiquidityBandsPacketProducer(unittest.TestCase):

    def setUp(self):
        self.valid_input = {
            "asset": "BTC",
            "timeframe": "5m",
            "session": "NY",
            "price": 64205.00,
            "nearest_upper_liquidity": 64200.00,
            "nearest_lower_liquidity": 63500.00,
            "liquidity_type": "prior_session_high",
            "distance_to_zone": -5.00,
            "distance_to_zone_pct": -0.007,
            "zone": "64200",
            "current_behavior": "Price interacting with zone.",
            "structure_context": "Divergence building on CVD footprint.",
            "sweep_status": "not_swept",
            "reaction_status": "no_reaction",
            "risk_mode": "Standard execution mode."
        }

    def test_sample_input_produces_valid_packet(self):
        input_data = parse_liquidity_bands_input(self.valid_input)
        packet = generate_liquidity_bands_packet(input_data)
        
        self.assertEqual(packet["v"], 1)
        self.assertEqual(packet["source_system"], "liquidity_bands_packet_producer")
        self.assertEqual(packet["source_role"], "liquidity_bands")
        self.assertEqual(packet["event_type"], "liquidity_sweep_watch")

    def test_packet_passes_egress_schema_validation(self):
        input_data = parse_liquidity_bands_input(self.valid_input)
        packet = generate_liquidity_bands_packet(input_data)
        try:
            validate_packet_dict(packet)
        except Exception as e:
            self.fail(f"Packet failed egress schema validation: {e}")

    def test_sweeping_now_severity_elevation(self):
        data = self.valid_input.copy()
        data["sweep_status"] = "sweeping_now"
        input_data = parse_liquidity_bands_input(data)
        packet = generate_liquidity_bands_packet(input_data)
        
        self.assertEqual(packet["severity"], "important")

    def test_reaction_status_acceptance_override(self):
        data = self.valid_input.copy()
        data["reaction_status"] = "acceptance"
        input_data = parse_liquidity_bands_input(data)
        packet = generate_liquidity_bands_packet(input_data)
        
        self.assertEqual(packet["risk_mode"], "Warning: Level may be failing. Acceptance observed.")

    def test_reaction_status_chop_override(self):
        data = self.valid_input.copy()
        data["reaction_status"] = "chop"
        input_data = parse_liquidity_bands_input(data)
        packet = generate_liquidity_bands_packet(input_data)
        
        self.assertEqual(packet["risk_mode"], "No chase. Chop risk.")

    def test_reaction_status_clean_rejection_injection(self):
        data = self.valid_input.copy()
        data["reaction_status"] = "clean_rejection"
        input_data = parse_liquidity_bands_input(data)
        packet = generate_liquidity_bands_packet(input_data)
        
        self.assertIn("Clean rejection observed", packet["confirmation_needed"])

    def test_forbidden_language_fails_closed(self):
        bad_input = self.valid_input.copy()
        bad_input["current_behavior"] = "You must enter a long here, it's easy money."
        
        input_data = parse_liquidity_bands_input(bad_input)
        with self.assertRaisesRegex(InputValidationError, "Forbidden language detected"):
            generate_liquidity_bands_packet(input_data)

    @patch('analysts.liquidity_bands_packet_producer.cli.OUTPUTS_DIR')
    @patch('analysts.liquidity_bands_packet_producer.cli.LOGS_DIR')
    def test_cli_outputs_are_written(self, mock_logs_dir, mock_outputs_dir):
        from analysts.liquidity_bands_packet_producer.cli import main
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_outputs_dir.return_value = tmp_path
            mock_outputs_dir.__truediv__.return_value = tmp_path / "latest_liquidity_bands_packet.json"
            mock_outputs_dir.mkdir = MagicMock()
            
            mock_logs_dir.return_value = tmp_path
            mock_logs_dir.__truediv__.return_value = tmp_path / "liquidity_bands_packet_producer.jsonl"
            mock_logs_dir.mkdir = MagicMock()

            sample_path = tmp_path / "test_input.json"
            with open(sample_path, "w") as f:
                json.dump(self.valid_input, f)

            with patch.object(sys, 'argv', ['cli', 'produce', '--file', str(sample_path)]):
                main()

            out_file = tmp_path / "latest_liquidity_bands_packet.json"
            self.assertTrue(out_file.exists())
            
            log_file = tmp_path / "liquidity_bands_packet_producer.jsonl"
            self.assertTrue(log_file.exists())

if __name__ == '__main__':
    unittest.main()
