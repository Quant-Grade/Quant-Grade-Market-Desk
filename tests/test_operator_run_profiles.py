import unittest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from ops.operator_run_profiles.runner import run_operator_profile
from ops.operator_run_profiles.schemas import OperatorError

class TestOperatorRunProfiles(unittest.TestCase):

    @patch('ops.operator_run_profiles.runner._run_subprocess')
    def test_dry_run_latest_profile(self, mock_run):
        mock_run.return_value = 0
        
        result = run_operator_profile("dry_run_latest", "BTC-USDT-SWAP")
        
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.profile_used, "dry_run_latest")
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        
        self.assertIn("--input-mode", cmd)
        self.assertIn("latest", cmd)
        self.assertIn("--dry-run", cmd)
        self.assertNotIn("--send", cmd)

    @patch('ops.operator_run_profiles.runner._run_subprocess')
    def test_send_if_allowed_latest_profile(self, mock_run):
        mock_run.return_value = 0
        
        result = run_operator_profile("send_if_allowed_latest", "BTC-USDT-SWAP")
        
        self.assertEqual(result.status, "SUCCESS")
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        
        self.assertIn("--input-mode", cmd)
        self.assertIn("latest", cmd)
        self.assertIn("--send", cmd)
        self.assertNotIn("--dry-run", cmd)

    @patch('ops.operator_run_profiles.runner._run_subprocess')
    def test_debug_latest_profile(self, mock_run):
        mock_run.return_value = 0
        
        result = run_operator_profile("debug_latest", "BTC-USDT-SWAP")
        
        self.assertEqual(result.status, "SUCCESS")
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        
        self.assertIn("--input-mode", cmd)
        self.assertIn("latest", cmd)
        self.assertIn("--dry-run", cmd)

    @patch('ops.operator_run_profiles.runner._run_subprocess')
    def test_status_only_does_not_invoke_pipeline(self, mock_run):
        with patch('pathlib.Path.exists', return_value=False):
            result = run_operator_profile("status_only")
        
        self.assertEqual(result.status, "SUCCESS")
        self.assertTrue(result.details["status_only"])
        mock_run.assert_not_called()

    def test_unknown_profile_fails_closed(self):
        with self.assertRaises(OperatorError):
            run_operator_profile("invalid_profile_name")

    @patch('ops.operator_run_profiles.runner._run_subprocess')
    def test_pipeline_failure_propagates(self, mock_run):
        mock_run.return_value = 1
        
        result = run_operator_profile("dry_run_latest")
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.pipeline_exit_code, 1)

if __name__ == '__main__':
    unittest.main()
