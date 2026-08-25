import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "rollout-trigger-learning.yml"


class RolloutTriggerLearningWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_reuses_frozen_oracle_artifact_without_running_physics(self):
        self.assertIn("source_run_id:", self.text)
        self.assertIn("actions/download-artifact@v4", self.text)
        self.assertIn("terminal-hard-state-aggregate-", self.text)
        self.assertNotIn("run_terminal_rollout_policy.py", self.text)
        self.assertNotIn("requirements-simulator.txt", self.text)

    def test_trains_only_the_trigger_with_group_holdout(self):
        self.assertIn("scripts/train_rollout_trigger.py", self.text)
        self.assertIn("--folds 4", self.text)
        self.assertIn("--ensemble-size 3", self.text)
        self.assertIn("--repeats 3", self.text)
        self.assertIn("requirements-learning.txt", self.text)
        self.assertNotIn("train_self_play_set_value.py", self.text)
        self.assertNotIn("--leaf-eval value", self.text)

    def test_push_trigger_is_scoped_to_the_cheap_learner(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("push:", self.text)
        self.assertIn(
            "- .github/workflows/rollout-trigger-learning.yml", self.text
        )
        self.assertIn("- scripts/train_rollout_trigger.py", self.text)
        self.assertNotIn("run_terminal_rollout_policy.py", self.text)
        self.assertLess(
            self.text.index("      epochs:"),
            self.text.index("  # Register this experiment workflow"),
        )


if __name__ == "__main__":
    unittest.main()
