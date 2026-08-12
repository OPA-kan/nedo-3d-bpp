import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "counterfactual-graph-scale.yml"


class CounterfactualGraphWorkflowTests(unittest.TestCase):
    def test_uses_the_latest_root_that_the_episode_actually_reached(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("root_steps:"), 8)
        self.assertIn('root_steps: "12 15"', text)
        self.assertIn('root_steps: "9 12"', text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("-name 'step-*-state.json'", text)
        self.assertIn("sort | tail -n 1", text)
        self.assertIn("steps.root.outputs.snapshot", text)

    def test_partial_condition_matrix_cannot_be_published(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("--expected-graphs 8", text)


if __name__ == "__main__":
    unittest.main()
