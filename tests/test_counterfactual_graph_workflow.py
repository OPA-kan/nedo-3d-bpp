import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "counterfactual-graph-scale.yml"


class CounterfactualGraphWorkflowTests(unittest.TestCase):
    def test_expands_every_reached_root_without_sampling_candidates(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("root_steps:"), 8)
        self.assertIn('root_steps: "12 15"', text)
        self.assertIn('root_steps: "9 12"', text)
        self.assertIn("--snapshot-only", text)
        self.assertNotIn("continue-on-error: true", text)
        self.assertIn("-name 'step-*-state.json'", text)
        self.assertIn('for snapshot in "${snapshots[@]}"', text)
        self.assertIn('"$graph_dir/graph.json"', text)

    def test_partial_condition_matrix_cannot_be_published(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("--expected-graphs 16"), 2)


if __name__ == "__main__":
    unittest.main()
