import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" /
    "terminal-rollout-policy-ablation.yml"
)


class TerminalRolloutPolicyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_paired_policies_without_value_model(self):
        self.assertIn("workflow_dispatch", self.text)
        self.assertEqual(self.text.count("--policy legacy"), 1)
        self.assertEqual(self.text.count("--policy terminal-rollout"), 1)
        self.assertNotIn("--leaf-eval value", self.text)
        self.assertNotIn("--model-dir", self.text)
        self.assertIn("environment-seed 42", self.text)

    def test_uses_all_six_preregistered_cells(self):
        for cell in (
            "dual-empty-original",
            "dual-preloaded-dedicated-source-001",
            "dual-shelf-mixed-source-001",
            "single-empty-noshelf-original",
            "single-empty-shelf-original",
            "single-preloaded-original",
        ):
            self.assertIn(f"cell: {cell}", self.text)

    def test_aggregate_requires_all_pairs(self):
        self.assertIn("needs: paired-cell", self.text)
        self.assertIn("aggregate_terminal_rollout_policy.py", self.text)
        self.assertIn("--expected-cells 6", self.text)
        self.assertIn("baseline.json", self.text)
        self.assertIn("rollout.json", self.text)
        self.assertIn("build_terminal_rollout_trigger_dataset.py", self.text)
        self.assertIn("trigger-dataset.json", self.text)


if __name__ == "__main__":
    unittest.main()
