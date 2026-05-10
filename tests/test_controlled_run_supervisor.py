import unittest
from unittest.mock import patch, MagicMock

from ops.controlled_run_supervisor.supervisor import run_supervisor
from ops.controlled_run_supervisor.schemas import SupervisorError
from ops.operator_run_profiles.schemas import OperatorResult

class TestControlledRunSupervisor(unittest.TestCase):

    @patch('time.sleep')
    @patch('ops.controlled_run_supervisor.supervisor.run_operator_profile')
    def test_supervisor_runs_exactly_max_runs(self, mock_run, mock_sleep):
        # Mock successful runs
        success_result = OperatorResult(run_id="test_run", profile_used="dry_run_latest")
        success_result.status = "SUCCESS"
        mock_run.return_value = success_result
        
        result = run_supervisor(
            profile="dry_run_latest",
            symbol="BTC",
            interval_seconds=5,
            max_runs=3
        )
        
        self.assertEqual(result.runs_completed, 3)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(mock_run.call_count, 3)
        # Sleep should happen max_runs - 1 times
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('time.sleep')
    @patch('ops.controlled_run_supervisor.supervisor.run_operator_profile')
    def test_failure_stops_supervisor_unless_continue_on_error(self, mock_run, mock_sleep):
        fail_result = OperatorResult(run_id="test_fail", profile_used="dry_run_latest")
        fail_result.status = "FAILED"
        mock_run.return_value = fail_result
        
        result = run_supervisor(
            profile="dry_run_latest",
            max_runs=3,
            continue_on_error=False
        )
        
        self.assertEqual(result.runs_completed, 1)
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(mock_sleep.call_count, 0)

    @patch('time.sleep')
    @patch('ops.controlled_run_supervisor.supervisor.run_operator_profile')
    def test_continue_on_error_records_failure_and_continues(self, mock_run, mock_sleep):
        fail_result = OperatorResult(run_id="test_fail", profile_used="dry_run_latest")
        fail_result.status = "FAILED"
        mock_run.return_value = fail_result
        
        result = run_supervisor(
            profile="dry_run_latest",
            max_runs=3,
            continue_on_error=True
        )
        
        self.assertEqual(result.runs_completed, 3)
        self.assertEqual(result.status, "SUCCESS") # The supervisor succeeded in finishing its bounds
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_missing_max_runs_fails_closed(self):
        with self.assertRaises(SupervisorError):
            run_supervisor(profile="dry_run_latest", max_runs=0)
            
        with self.assertRaises(SupervisorError):
            run_supervisor(profile="dry_run_latest", max_runs=None)

if __name__ == '__main__':
    unittest.main()
