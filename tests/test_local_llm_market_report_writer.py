import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from integrations.discord_webhook_egress.schemas import validate_packet_dict, AlertPacket
from analysts.local_llm_market_report_writer.schemas import InputValidationError, HallucinationError
from analysts.local_llm_market_report_writer.writer import write_market_report

class TestLocalLLMMarketReportWriter(unittest.TestCase):

    def setUp(self):
        self.input_packet_dict = {
            "v": 1,
            "packet_id": "multi_123",
            "created_at": "2026-05-10T08:00:00Z",
            "source_system": "multi_role_market_read_combiner",
            "source_role": "multi_role",
            "asset": "BTC",
            "timeframe": "1m",
            "session": "NY",
            "event_type": "multi_role_market_read",
            "severity": "important",
            "headline": "Multi-Role Market Read: BTC",
            "summary": "Amalgamated scenario.",
            "evidence_packets": ["[VWAP] evidence", "[SESSION] evidence"],
            "rag_refs": [],
            "memory_refs": [],
            "confirmation_needed": "VWAP confirmation required.",
            "invalidation": "Loss of confluence.",
            "risk_mode": "Mixed evidence.",
            "retail_translation": "Multiple indicators.",
            "leader_decision": "LD.",
            "scribe_note": "Note.",
            "not_financial_advice": True
        }
        self.input_packet = validate_packet_dict(self.input_packet_dict)
        
        self.valid_mock_llm_json = json.dumps({
            "headline": "LLM Refined Headline",
            "summary": "LLM refined summary.",
            "evidence_packets": ["Refined evidence 1", "Refined evidence 2"],
            "retail_translation": "Refined retail translation.",
            "confirmation_needed": "VWAP confirmation required.",
            "invalidation": "Loss of confluence.",
            "risk_mode": "Mixed evidence."
        })

    def test_mock_llm_creates_valid_packet(self):
        packet = write_market_report(self.input_packet, mock_llm_response=self.valid_mock_llm_json)
        self.assertEqual(packet["v"], 1)
        self.assertEqual(packet["source_system"], "local_llm_market_report_writer")
        self.assertEqual(packet["headline"], "LLM Refined Headline")
        try:
            validate_packet_dict(packet)
        except Exception as e:
            self.fail(f"LLM output failed structural validation: {e}")

    def test_invalid_json_fails_closed(self):
        bad_json = "{ bad json"
        with self.assertRaisesRegex(InputValidationError, "invalid JSON"):
            write_market_report(self.input_packet, mock_llm_response=bad_json)

    def test_missing_required_fields_fails_closed(self):
        incomplete_json = json.dumps({
            "headline": "LLM Refined Headline"
            # Missing summary, evidence, etc.
        })
        with self.assertRaisesRegex(InputValidationError, "omitted required field"):
            write_market_report(self.input_packet, mock_llm_response=incomplete_json)

    def test_forbidden_language_fails_closed(self):
        bad_llm_json = json.dumps({
            "headline": "Guaranteed Signal",
            "summary": "You must enter here for easy money.",
            "evidence_packets": [],
            "retail_translation": "Buy here.",
            "confirmation_needed": "None",
            "invalidation": "None",
            "risk_mode": "None"
        })
        with self.assertRaisesRegex(InputValidationError, "Forbidden language"):
            write_market_report(self.input_packet, mock_llm_response=bad_llm_json)

    def test_hallucinated_unsupported_field_fails_closed(self):
        hallucinated_json = json.dumps({
            "headline": "LLM Refined Headline",
            "summary": "LLM refined summary.",
            "evidence_packets": [],
            "retail_translation": "Translation.",
            "confirmation_needed": "Conf.",
            "invalidation": "Inv.",
            "risk_mode": "Risk.",
            "fake_field_price_target": "100k"
        })
        with self.assertRaisesRegex(HallucinationError, "hallucinated unsupported field: fake_field_price_target"):
            write_market_report(self.input_packet, mock_llm_response=hallucinated_json)

    @patch('analysts.local_llm_market_report_writer.cli.OUTPUTS_DIR')
    @patch('analysts.local_llm_market_report_writer.cli.LOGS_DIR')
    @patch('analysts.local_llm_market_report_writer.cli.write_market_report')
    def test_cli_outputs_are_written(self, mock_write_report, mock_logs_dir, mock_outputs_dir):
        from analysts.local_llm_market_report_writer.cli import main
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            mock_outputs_dir.return_value = tmp_path
            mock_outputs_dir.__truediv__.return_value = tmp_path / "latest_llm_market_report_packet.json"
            mock_outputs_dir.mkdir = MagicMock()
            
            mock_logs_dir.return_value = tmp_path
            mock_logs_dir.__truediv__.return_value = tmp_path / "local_llm_market_report_writer.jsonl"
            mock_logs_dir.mkdir = MagicMock()

            # Mock the return packet from the writer
            valid_packet = validate_packet_dict(self.input_packet_dict)
            mock_write_report.return_value = self.input_packet_dict
            
            sample_path = tmp_path / "test_input.json"
            with open(sample_path, "w") as f:
                json.dump(self.input_packet_dict, f)

            with patch.object(sys, 'argv', ['cli', 'write', '--input', str(sample_path)]):
                main()

            out_file = tmp_path / "latest_llm_market_report_packet.json"
            self.assertTrue(out_file.exists())
            
            log_file = tmp_path / "local_llm_market_report_writer.jsonl"
            self.assertTrue(log_file.exists())

    @patch('urllib.request.urlopen')
    def test_payload_excludes_response_format(self, mock_urlopen):
        from analysts.local_llm_market_report_writer.llm_client import query_local_llm
        
        # Setup mock to return a valid dummy response so json parsing doesn't crash
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "{}"}}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        query_local_llm("sys", "user")
        
        # Check what was passed into urlopen
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        
        # Extract payload
        payload_data = json.loads(req.data.decode("utf-8"))
        self.assertNotIn("response_format", payload_data, "Payload must not contain response_format")

if __name__ == '__main__':
    unittest.main()
