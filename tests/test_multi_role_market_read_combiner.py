import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from integrations.discord_webhook_egress.schemas import validate_packet_dict
from analysts.multi_role_market_read_combiner.schemas import load_source_packet, CombinerValidationError, InputValidationError
from analysts.multi_role_market_read_combiner.combiner import generate_multi_role_packet

class TestMultiRoleCombiner(unittest.TestCase):

    def setUp(self):
        self.vwap_packet = {
            "v": 1,
            "packet_id": "vwap_001",
            "created_at": "2026-05-10T08:00:00Z",
            "source_system": "vwap_packet_producer",
            "source_role": "vwap",
            "asset": "BTC",
            "timeframe": "1m",
            "session": "NY",
            "event_type": "vwap_watch",
            "severity": "watch",
            "headline": "BTC VWAP",
            "summary": "VWAP summary.",
            "evidence_packets": ["VWAP ev 1"],
            "rag_refs": [],
            "memory_refs": [],
            "confirmation_needed": "None.",
            "invalidation": "Inv.",
            "risk_mode": "Standard execution mode.",
            "retail_translation": "Trans.",
            "leader_decision": "LD.",
            "scribe_note": "Note.",
            "not_financial_advice": True
        }
        
        self.session_packet = self.vwap_packet.copy()
        self.session_packet["packet_id"] = "sess_001"
        self.session_packet["source_role"] = "session_open"
        self.session_packet["event_type"] = "session_open_brief"
        self.session_packet["severity"] = "info"
        self.session_packet["risk_mode"] = "Standard execution mode."
        
        self.liq_packet = self.vwap_packet.copy()
        self.liq_packet["packet_id"] = "liq_001"
        self.liq_packet["source_role"] = "liquidity_bands"
        self.liq_packet["event_type"] = "liquidity_sweep_watch"
        self.liq_packet["severity"] = "important"
        self.liq_packet["risk_mode"] = "Standard execution mode."
        
    def _create_temp_files(self, tmp_path):
        v_path = tmp_path / "vwap.json"
        s_path = tmp_path / "sess.json"
        l_path = tmp_path / "liq.json"
        with open(v_path, "w") as f: json.dump(self.vwap_packet, f)
        with open(s_path, "w") as f: json.dump(self.session_packet, f)
        with open(l_path, "w") as f: json.dump(self.liq_packet, f)
        return v_path, s_path, l_path

    def test_combined_packet_passes_schema_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path, s_path, l_path = self._create_temp_files(Path(tmpdir))
            vp = load_source_packet(str(v_path))
            sp = load_source_packet(str(s_path))
            lp = load_source_packet(str(l_path))
            
            combined = generate_multi_role_packet(vp, sp, lp)
            
            try:
                validate_packet_dict(combined)
            except Exception as e:
                self.fail(f"Combined packet failed schema validation: {e}")
                
            self.assertEqual(combined["event_type"], "multi_role_market_read")
            self.assertEqual(combined["source_role"], "multi_role")

    def test_mixed_severity_chooses_highest(self):
        # We have watch, info, important. Expected: important
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path, s_path, l_path = self._create_temp_files(Path(tmpdir))
            vp = load_source_packet(str(v_path))
            sp = load_source_packet(str(s_path))
            lp = load_source_packet(str(l_path))
            
            combined = generate_multi_role_packet(vp, sp, lp)
            self.assertEqual(combined["severity"], "important")

    def test_asset_mismatch_fails_closed(self):
        self.session_packet["asset"] = "ETH"
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path, s_path, l_path = self._create_temp_files(Path(tmpdir))
            vp = load_source_packet(str(v_path))
            sp = load_source_packet(str(s_path))
            lp = load_source_packet(str(l_path))
            
            with self.assertRaisesRegex(CombinerValidationError, "Asset mismatch"):
                generate_multi_role_packet(vp, sp, lp)

    def test_missing_packet_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with self.assertRaises(CombinerValidationError):
                load_source_packet(str(tmp_path / "does_not_exist.json"))

    def test_forbidden_language_fails_closed(self):
        self.vwap_packet["evidence_packets"] = ["This is a guaranteed signal."]
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path, s_path, l_path = self._create_temp_files(Path(tmpdir))
            vp = load_source_packet(str(v_path))
            sp = load_source_packet(str(s_path))
            lp = load_source_packet(str(l_path))
            
            with self.assertRaisesRegex(InputValidationError, "Forbidden language"):
                generate_multi_role_packet(vp, sp, lp)

    def test_mixed_evidence_risk_mode_overrides(self):
        # Trigger mixed evidence by having different risk modes
        self.session_packet["risk_mode"] = "Elevated volatility."
        with tempfile.TemporaryDirectory() as tmpdir:
            v_path, s_path, l_path = self._create_temp_files(Path(tmpdir))
            vp = load_source_packet(str(v_path))
            sp = load_source_packet(str(s_path))
            lp = load_source_packet(str(l_path))
            
            combined = generate_multi_role_packet(vp, sp, lp)
            self.assertIn("Mixed evidence. Watch only. Confirmation required.", combined["risk_mode"])
            self.assertIn("Open-window volatility risk.", combined["risk_mode"])

    @patch('analysts.multi_role_market_read_combiner.cli.OUTPUTS_DIR')
    @patch('analysts.multi_role_market_read_combiner.cli.LOGS_DIR')
    def test_cli_outputs_are_written(self, mock_logs_dir, mock_outputs_dir):
        from analysts.multi_role_market_read_combiner.cli import main
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_outputs_dir.return_value = tmp_path
            mock_outputs_dir.__truediv__.return_value = tmp_path / "latest_multi_role_market_read_packet.json"
            mock_outputs_dir.mkdir = MagicMock()
            
            mock_logs_dir.return_value = tmp_path
            mock_logs_dir.__truediv__.return_value = tmp_path / "multi_role_market_read_combiner.jsonl"
            mock_logs_dir.mkdir = MagicMock()

            v_path, s_path, l_path = self._create_temp_files(tmp_path)

            with patch.object(sys, 'argv', ['cli', 'combine', '--vwap', str(v_path), '--session', str(s_path), '--liquidity', str(l_path)]):
                main()

            out_file = tmp_path / "latest_multi_role_market_read_packet.json"
            self.assertTrue(out_file.exists())
            
            log_file = tmp_path / "multi_role_market_read_combiner.jsonl"
            self.assertTrue(log_file.exists())

if __name__ == '__main__':
    unittest.main()
