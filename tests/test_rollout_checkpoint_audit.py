import subprocess
import sys
import unittest

from scripts.audit_rollout_checkpoints import (
    choose_checkpoint_candidate,
    summarize_roots,
)


class RolloutCheckpointAuditTests(unittest.TestCase):
    def test_conservative_selection_keeps_incumbent_on_frontier(self):
        self.assertEqual(
            choose_checkpoint_candidate(
                ["inc", "alt"], incumbent="inc", frontier=["inc", "alt"]
            ),
            "inc",
        )
        self.assertEqual(
            choose_checkpoint_candidate(
                ["inc", "alt"], incumbent="inc", frontier=["alt"]
            ),
            "alt",
        )

    def test_summary_reports_terminal_recall_and_wall_clock(self):
        roots = [{
            "incumbent_candidate_id": "inc",
            "terminal_selected_candidate_id": "alt",
            "checkpoints": {
                "0": {
                    "selected_candidate_id": "inc",
                    "estimated_decision_seconds": 4.0,
                },
                "2": {
                    "selected_candidate_id": "alt",
                    "estimated_decision_seconds": 9.0,
                },
            },
        }]
        summary = summarize_roots(roots, [0, 2])
        self.assertEqual(summary["0"]["intervention_action_recall"], 0.0)
        self.assertEqual(summary["2"]["intervention_action_recall"], 1.0)
        self.assertEqual(summary["2"]["within_10s_rate"], 1.0)

    def test_script_can_run_directly(self):
        result = subprocess.run(
            [sys.executable, "scripts/audit_rollout_checkpoints.py", "--help"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--trigger-dataset", result.stdout)


if __name__ == "__main__":
    unittest.main()
