import unittest
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from integrations.discord_webhook_egress.schemas import validate_packet_dict, AlertPacket
from policy.alert_policy_gate.gate import evaluate_packet

class TestAlertPolicyGate(unittest.TestCase):

    def setUp(self):
        self.input_packet_dict = {
            "v": 1,
            "packet_id": "test_pkt_123",
            "created_at": "2026-05-10T08:00:00Z",
            "source_system": "local_llm_market_report_writer",
            "source_role": "multi_role",
            "asset": "BTC",
            "timeframe": "1m",
            "session": "NY",
            "event_type": "multi_role_market_read",
            "severity": "important",
            "headline": "BTC Market Read",
            "summary": "Summary.",
            "evidence_packets": ["Evidence"],
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
        self.packet = validate_packet_dict(self.input_packet_dict)

    @patch('policy.alert_policy_gate.gate.is_duplicate')
    @patch('policy.alert_policy_gate.gate.get_last_event_time')
    def test_valid_important_returns_allow(self, mock_last_event, mock_duplicate):
        mock_duplicate.return_value = False
        mock_last_event.return_value = 0.0 # Way past cooldown
        
        decision = evaluate_packet(self.packet)
        self.assertEqual(decision["status"], "ALLOW_SEND")

    @patch('policy.alert_policy_gate.gate.is_duplicate')
    def test_duplicate_returns_block(self, mock_duplicate):
        mock_duplicate.return_value = True
        
        decision = evaluate_packet(self.packet)
        self.assertEqual(decision["status"], "BLOCK_DUPLICATE")

    @patch('policy.alert_policy_gate.gate.is_duplicate')
    @patch('policy.alert_policy_gate.gate.get_last_event_time')
    def test_cooldown_returns_block(self, mock_last_event, mock_duplicate):
        mock_duplicate.return_value = False
        mock_last_event.return_value = time.time() - 100 # Sent 100s ago (inside cooldown)
        
        decision = evaluate_packet(self.packet)
        self.assertEqual(decision["status"], "BLOCK_COOLDOWN")

    def test_info_returns_block(self):
        self.input_packet_dict["severity"] = "info"
        info_pkt = validate_packet_dict(self.input_packet_dict)
        
        decision = evaluate_packet(info_pkt)
        self.assertEqual(decision["status"], "BLOCK_LOW_SEVERITY")

    def test_watch_returns_downgrade(self):
        self.input_packet_dict["severity"] = "watch"
        watch_pkt = validate_packet_dict(self.input_packet_dict)
        
        decision = evaluate_packet(watch_pkt)
        self.assertEqual(decision["status"], "DOWNGRADE_DRY_RUN_ONLY")

    def test_unsafe_returns_block(self):
        # We simulate an unsafe packet by passing a packet that lacks keys at the dictionary level before it got converted to AlertPacket,
        # but since we must pass an AlertPacket to evaluate_packet, we just manually break it.
        broken_pkt = validate_packet_dict(self.input_packet_dict)
        broken_pkt.event_type = "invalid_event" # Will fail schema validation inside gate
        
        decision = evaluate_packet(broken_pkt)
        self.assertEqual(decision["status"], "BLOCK_UNSAFE")

    @patch('policy.alert_policy_gate.gate.is_duplicate')
    @patch('policy.alert_policy_gate.gate.get_last_event_time')
    def test_original_packet_immutable(self, mock_last_event, mock_duplicate):
        mock_duplicate.return_value = False
        mock_last_event.return_value = 0.0
        
        original_dict = self.packet.__dict__.copy()
        evaluate_packet(self.packet)
        self.assertEqual(self.packet.__dict__, original_dict)

if __name__ == '__main__':
    unittest.main()
