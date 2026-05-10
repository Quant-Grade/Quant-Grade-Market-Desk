import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from pipelines.market_report_pipeline_runner.runner import execute_pipeline
from pipelines.market_report_pipeline_runner.schemas import PipelineResult

class TestMarketReportPipelineRunner(unittest.TestCase):

    def setUp(self):
        self.mock_policy_decision = {
            "status": "ALLOW_SEND",
            "reason": "Clear",
            "packet_id": "test1234"
        }

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_dry_run_pipeline_executes_correct_order(self, mock_run, mock_open):
        # Mock the policy read
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        mock_run.return_value = MagicMock()
        
        result = execute_pipeline(send=False, dry_run=True, skip_llm=False, input_mode="sample")
        
        # Check order
        self.assertEqual(result.steps_run[0], "vwap_packet_producer")
        self.assertEqual(result.steps_run[1], "session_open_packet_producer")
        self.assertEqual(result.steps_run[2], "liquidity_bands_packet_producer")
        self.assertEqual(result.steps_run[3], "multi_role_market_read_combiner")
        self.assertEqual(result.steps_run[4], "local_llm_market_report_writer")
        self.assertEqual(result.steps_run[5], "alert_policy_gate")
        self.assertEqual(result.steps_run[6], "discord_webhook_egress_dry_run")
        
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.egress_action, "DRY_RUN")

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_default_mode_does_not_send(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        
        from pipelines.market_report_pipeline_runner.cli import main
        import sys
        
        with patch.object(sys, 'argv', ['cli', 'run']):
            with patch('pipelines.market_report_pipeline_runner.cli.append_log'):
                with patch('pipelines.market_report_pipeline_runner.cli.OUTPUTS_DIR'):
                    try:
                        main()
                    except SystemExit as e:
                        self.assertEqual(e.code, 0)
                        
        # Ensure no call in mock_run contains "send" for discord_webhook_egress
        for c in mock_run.call_args_list:
            args = c[0][0]
            if "integrations.discord_webhook_egress.cli" in args:
                self.assertNotIn("send", args)
                self.assertIn("dry-run", args)

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_allow_send_without_flag_dry_runs(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        result = execute_pipeline(send=False)
        self.assertEqual(result.egress_action, "DRY_RUN")

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_blocked_policy_prevents_egress(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"status": "BLOCK_UNSAFE"})
        result = execute_pipeline(send=True)
        self.assertEqual(result.egress_action, "BLOCKED")
        self.assertIn("egress_skipped_due_to_block", result.steps_run)

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_duplicate_policy_prevents_egress(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"status": "BLOCK_DUPLICATE"})
        result = execute_pipeline(send=True)
        self.assertEqual(result.egress_action, "BLOCKED")
        self.assertIn("egress_skipped_due_to_block", result.steps_run)

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_generated_mode_runs_snapshot_builder(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        mock_run.return_value = MagicMock()
        
        result = execute_pipeline(send=False, dry_run=True, skip_llm=False, input_mode="generated")
        
        # Check order starts with market_snapshot_builder
        self.assertEqual(result.steps_run[0], "market_snapshot_builder")
        self.assertEqual(result.steps_run[1], "vwap_packet_producer")
        self.assertTrue(result.snapshot_builder_ran)
        self.assertEqual(result.input_mode, "generated")
        self.assertIn("vwap", result.generated_input_paths)
        
        # Verify the subprocess call arguments include the generated paths
        call_args = [c[0][0] for c in mock_run.call_args_list]
        vwap_call = next(args for args in call_args if "vwap_packet_producer" in args[2])
        self.assertIn("--file", vwap_call)
        
    @patch('builtins.open')
    @patch('subprocess.run')
    def test_no_network_send_in_tests(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        result = execute_pipeline(send=False)
        # Check all subprocess calls to verify none try to send
        for c in mock_run.call_args_list:
            args = c[0][0]
            if "integrations.discord_webhook_egress.cli" in args:
                self.assertNotIn("send", args)

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_snapshot_input_passed_to_builder(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        mock_run.return_value = MagicMock()
        
        test_path = "path/to/test.parquet"
        result = execute_pipeline(send=False, dry_run=True, skip_llm=False, input_mode="generated", snapshot_input=test_path)
        
        self.assertTrue(result.used_real_ingestion_input)
        self.assertEqual(result.snapshot_input_path, test_path)
        self.assertEqual(result.snapshot_source_type, "parquet")
        
        # Verify the subprocess call arguments include the snapshot input
        call_args = [c[0][0] for c in mock_run.call_args_list]
        builder_call = next(args for args in call_args if "market_snapshot_builder" in args[2])
        self.assertIn("--input", builder_call)
        self.assertIn(test_path, builder_call)
        
    @patch('builtins.open')
    @patch('subprocess.run')
    def test_no_snapshot_input_uses_sample(self, mock_run, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
        mock_run.return_value = MagicMock()
        
        result = execute_pipeline(send=False, dry_run=True, skip_llm=False, input_mode="generated")
        
        self.assertFalse(result.used_real_ingestion_input)
        self.assertIsNone(result.snapshot_input_path)
        
        # Verify the subprocess call arguments include --sample
        call_args = [c[0][0] for c in mock_run.call_args_list]
        builder_call = next(args for args in call_args if "market_snapshot_builder" in args[2])
        self.assertIn("--sample", builder_call)
        self.assertNotIn("--input", builder_call)

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_latest_mode_runs_resolver_and_builder(self, mock_run, mock_open):
        def mock_open_side_effect(file, *args, **kwargs):
            m = MagicMock()
            if "latest_parquet_resolution.json" in str(file):
                m.__enter__.return_value.read.return_value = json.dumps({"resolved_path": "resolved/path.parquet"})
            else:
                m.__enter__.return_value.read.return_value = json.dumps(self.mock_policy_decision)
            return m
            
        mock_open.side_effect = mock_open_side_effect
        mock_run.return_value = MagicMock()
        
        result = execute_pipeline(send=False, dry_run=True, skip_llm=False, input_mode="latest", symbol="BTC-USDT-SWAP")
        
        self.assertTrue(result.latest_resolver_ran)
        self.assertTrue(result.used_real_ingestion_input)
        self.assertEqual(result.resolved_snapshot_input_path, "resolved/path.parquet")
        
        call_args = [c[0][0] for c in mock_run.call_args_list]
        
        # Check resolver ran first
        resolver_call = call_args[0]
        self.assertIn("latest_parquet_resolver", resolver_call[2])
        self.assertIn("--symbol", resolver_call)
        self.assertIn("BTC-USDT-SWAP", resolver_call)
        
        # Check builder ran second
        builder_call = call_args[1]
        self.assertIn("market_snapshot_builder", builder_call[2])
        self.assertIn("--input", builder_call)
        self.assertIn("resolved/path.parquet", builder_call)

if __name__ == '__main__':
    unittest.main()
