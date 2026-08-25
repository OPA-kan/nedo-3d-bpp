import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "rollout-checkpoint-oracle.yml"


class RolloutCheckpointWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_replays_wave3_cells_at_h1_h3_without_value(self):
        self.assertEqual(self.text.count("          - cell:"), 36)
        self.assertIn('default: "0,2"', self.text)
        self.assertIn("audit_rollout_checkpoints.py", self.text)
        self.assertNotIn("--leaf-eval value", self.text)
        self.assertNotIn("requirements-learning.txt", self.text)

    def test_reuses_frozen_terminal_truth_and_aggregates(self):
        self.assertIn("terminal-hard-state-aggregate-", self.text)
        self.assertIn("32813542943", self.text)
        self.assertIn("aggregate_rollout_checkpoints.py", self.text)
        self.assertIn("--expected-cells 36", self.text)
        self.assertIn("actions: read", self.text)

    def test_push_scope_does_not_recollect_behavior_trajectories(self):
        self.assertIn("push:", self.text)
        self.assertNotIn("run_terminal_rollout_policy.py", self.text)
        self.assertIn("scripts/audit_rollout_checkpoints.py", self.text)


if __name__ == "__main__":
    unittest.main()
