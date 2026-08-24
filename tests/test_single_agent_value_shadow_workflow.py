import pathlib
import unittest


class SingleAgentValueShadowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = pathlib.Path(
            ".github/workflows/single-agent-value-shadow.yml"
        ).read_text(encoding="utf-8")

    def test_trains_single_agent_oof_ensemble_before_physics(self):
        self.assertIn("build_single_agent_value_dataset.py", self.workflow)
        self.assertIn("train_self_play_set_value.py", self.workflow)
        self.assertIn("needs: train-value", self.workflow)
        self.assertIn("--ensemble-size 3", self.workflow)

    def test_comparison_changes_only_leaf_evaluation(self):
        self.assertEqual(self.workflow.count("--allocation pareto-puct"), 1)
        self.assertIn("--max-depth 2", self.workflow)
        self.assertIn("--leaf-eval measured", self.workflow)
        self.assertIn("--leaf-eval value", self.workflow)
        self.assertIn("--terminal-audit", self.workflow)
        self.assertIn("--item-symmetry-cache-shadow", self.workflow)
        self.assertIn("--look-ahead 40", self.workflow)
        self.assertNotIn("progressive", self.workflow.lower())

    def test_has_six_cells_and_terminal_scored_aggregate(self):
        self.assertEqual(self.workflow.count("- {cell:"), 6)
        self.assertIn("aggregate_single_agent_value_shadow.py", self.workflow)
        self.assertIn("--expected-cells 6", self.workflow)


if __name__ == "__main__":
    unittest.main()
