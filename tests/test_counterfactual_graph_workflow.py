import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "counterfactual-graph-scale.yml"
TIE_H5_WORKFLOW = (
    ROOT / ".github" / "workflows" / "counterfactual-graph-tie-depth.yml"
)


class CounterfactualGraphWorkflowTests(unittest.TestCase):
    def test_expands_every_reached_root_without_sampling_candidates(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("root_steps:"), 8)
        self.assertIn('root_steps: "6 12 15"', text)
        self.assertIn('root_steps: "6 9 12"', text)
        self.assertIn("--snapshot-only", text)
        self.assertNotIn("continue-on-error: true", text)
        self.assertIn("-name 'step-*-state.json'", text)
        self.assertIn('for snapshot in "${snapshots[@]}"', text)
        self.assertIn('"$graph_dir/graph.json"', text)

    def test_partial_condition_matrix_cannot_be_published(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("--minimum-graphs 16"), 2)
        self.assertEqual(text.count("--expected-conditions 8"), 2)
        self.assertIn("build_counterfactual_teacher_pairs.py", text)
        self.assertIn("evaluate_counterfactual_teacher_baseline.py", text)
        self.assertIn("evaluate_counterfactual_teacher_discovery.py", text)
        self.assertIn(
            "evaluate_counterfactual_teacher_frozen_policy.py", text
        )
        self.assertIn("aggregate/teacher-pairs", text)

    def test_h5_is_limited_to_three_known_root_level_ties(self):
        text = TIE_H5_WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("root_steps:"), 2)
        self.assertIn('root_steps: "6"', text)
        self.assertIn('root_steps: "6 9"', text)
        self.assertIn("--horizon 5", text)
        self.assertEqual(text.count("--expected-graphs 3"), 2)


if __name__ == "__main__":
    unittest.main()
