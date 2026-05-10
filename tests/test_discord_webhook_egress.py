import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from integrations.discord_webhook_egress.schemas import validate_packet_dict, parse_packet_file, SchemaValidationError
from integrations.discord_webhook_egress.formatter import format_discord_message
from integrations.discord_webhook_egress.safety import check_safety, SafetyViolationError
from integrations.discord_webhook_egress.client import send_to_discord
from integrations.discord_webhook_egress.storage import append_log, write_latest_message

class TestDiscordWebhookEgress(unittest.TestCase):

    def setUp(self):
        self.valid_packet_data = {
            "v": 1,
            "packet_id": "test_001",
            "created_at": "2026-05-10T07:00:00Z",
            "source_system": "local_llm_loop",
            "source_role": "vwap",
            "asset": "BTC",
            "timeframe": "1m",
            "session": "NY",
            "event_type": "vwap_watch",
            "severity": "watch",
            "headline": "Test Headline",
            "summary": "Test Summary",
            "evidence_packets": ["Ev 1"],
            "rag_refs": [],
            "memory_refs": [],
            "confirmation_needed": "Confirm",
            "invalidation": "Invalid",
            "risk_mode": "Watch",
            "retail_translation": "Translate",
            "leader_decision": "Decision",
            "scribe_note": "Note",
            "not_financial_advice": True
        }

    def test_json_packet_validation_fails_missing_v(self):
        data = self.valid_packet_data.copy()
        del data["v"]
        with self.assertRaisesRegex(SchemaValidationError, "first key must be 'v'"):
            validate_packet_dict(data)

    def test_json_packet_validation_fails_unknown_v(self):
        data = self.valid_packet_data.copy()
        data["v"] = 2
        # We need to re-insert v as the first key
        new_data = {"v": 2}
        new_data.update(data)
        with self.assertRaisesRegex(SchemaValidationError, "expected integer 1"):
            validate_packet_dict(new_data)

    def test_json_packet_validation_fails_v_type_drift(self):
        data = self.valid_packet_data.copy()
        data["v"] = "1"
        new_data = {"v": "1"}
        new_data.update(data)
        with self.assertRaisesRegex(SchemaValidationError, "expected integer 1"):
            validate_packet_dict(new_data)

    def test_formatter_includes_required_sections(self):
        packet = validate_packet_dict(self.valid_packet_data)
        output = format_discord_message(packet)
        self.assertIn("**[WATCH] BTC - VWAP_WATCH**", output)
        self.assertIn("**Session:** NY", output)
        self.assertIn("**Headline:**", output)
        self.assertIn("Test Headline", output)
        self.assertIn("**Evidence:**", output)
        self.assertIn("- Ev 1", output)
        self.assertIn("**Retail Translation:**", output)
        self.assertIn("*educational scenario only, not financial advice*", output)

    def test_unsafe_language_guard_blocks_forbidden_phrases(self):
        # "financial advice" is part of the normal footer, but our safety guard strips the standard footer string.
        # Let's insert a forbidden phrase elsewhere.
        with self.assertRaises(SafetyViolationError):
            check_safety("This is easy money right here.")
            
        with self.assertRaises(SafetyViolationError):
            check_safety("This is 100% guaranteed.")

        # Should pass with normal text
        try:
            check_safety("This is a safe message without the footer yet.")
        except SafetyViolationError:
            self.fail("check_safety raised SafetyViolationError unexpectedly")

    def test_oversized_message_blocks_send(self):
        from integrations.discord_webhook_egress.safety import check_length, MessageTooLongError
        oversized = "a" * 1901
        with self.assertRaisesRegex(MessageTooLongError, "Message is too long"):
            check_length(oversized)

        # Should pass with under 1900
        try:
            check_length("a" * 1900)
        except MessageTooLongError:
            self.fail("check_length raised MessageTooLongError unexpectedly")

    @patch('integrations.discord_webhook_egress.client.urllib.request.urlopen')
    def test_webhook_url_not_present_in_log_output(self, mock_urlopen):
        import urllib.error
        # Mock urlopen to raise a URLError with the webhook URL in the message
        fake_url = "https://discord.com/api/webhooks/12345/ABCDE"
        mock_urlopen.side_effect = urllib.error.URLError(f"Connection refused to {fake_url}")
        
        with self.assertRaises(Exception) as context:
            send_to_discord(fake_url, "Test content")
            
        error_msg = str(context.exception)
        self.assertNotIn(fake_url, error_msg)
        self.assertIn("<REDACTED_URL>", error_msg)

    @patch('integrations.discord_webhook_egress.client.urllib.request.urlopen')
    def test_missing_webhook_url_fails_safely_on_send(self, mock_urlopen):
        with self.assertRaisesRegex(ValueError, "Webhook URL is missing"):
            send_to_discord("", "Test content")

    def test_sample_packets_validate(self):
        base_dir = Path(__file__).resolve().parent.parent / "integrations" / "discord_webhook_egress" / "sample_packets"
        for sample in ["vwap_watch", "session_open_brief", "multi_role_market_read"]:
            file_path = base_dir / f"{sample}.json"
            if file_path.exists():
                try:
                    packet = parse_packet_file(str(file_path))
                    self.assertEqual(packet.v, 1)
                except Exception as e:
                    self.fail(f"Sample packet {sample} failed to validate: {e}")

    @patch('integrations.discord_webhook_egress.storage.LOGS_DIR')
    @patch('integrations.discord_webhook_egress.storage.OUTPUTS_DIR')
    def test_send_log_appends_jsonl_records(self, mock_outputs_dir, mock_logs_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_logs_dir.return_value = tmp_path
            mock_logs_dir.__truediv__.return_value = tmp_path / "discord_webhook_egress.jsonl"
            mock_logs_dir.mkdir = MagicMock()
            
            append_log("test_001", "send", "success")
            
            log_file = tmp_path / "discord_webhook_egress.jsonl"
            self.assertTrue(log_file.exists())
            with open(log_file, "r") as f:
                content = f.read()
                data = json.loads(content)
                self.assertEqual(data["packet_id"], "test_001")
                self.assertEqual(data["status"], "success")

    @patch('integrations.discord_webhook_egress.storage.LOGS_DIR')
    @patch('integrations.discord_webhook_egress.storage.OUTPUTS_DIR')
    def test_latest_rendered_markdown_output_is_written(self, mock_outputs_dir, mock_logs_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_outputs_dir.return_value = tmp_path
            mock_outputs_dir.__truediv__.return_value = tmp_path / "latest_discord_webhook_message.md"
            mock_outputs_dir.mkdir = MagicMock()
            
            write_latest_message("Rendered Output Test")
            
            out_file = tmp_path / "latest_discord_webhook_message.md"
            self.assertTrue(out_file.exists())
            with open(out_file, "r") as f:
                self.assertEqual(f.read(), "Rendered Output Test")

if __name__ == '__main__':
    unittest.main()
