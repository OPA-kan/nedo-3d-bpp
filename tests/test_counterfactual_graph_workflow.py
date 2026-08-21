import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "counterfactual-graph-scale.yml"
TIE_H5_WORKFLOW = (
    ROOT / ".github" / "workflows" / "counterfactual-graph-tie-depth.yml"
)
BRANCH_WIDTH_WORKFLOW = (
    ROOT / ".github" / "workflows" /
    "counterfactual-graph-branch-width.yml"
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
        self.assertIn("graph_branch_factor:", text)
        self.assertIn("graph_horizon:", text)
        self.assertIn("measurement_only:", text)
        self.assertIn('branch_factor="${{ inputs.graph_branch_factor || \'3\' }}"', text)
        self.assertIn('horizon="${{ inputs.graph_horizon || \'3\' }}"', text)
        self.assertIn('if [[ "$horizon" == "4" ]]', text)
        self.assertIn("max_nodes=121", text)
        self.assertIn('--horizon "$horizon"', text)
        self.assertIn("--expected-horizon ${{ inputs.graph_horizon || '3' }}", text)
        self.assertIn("--expected-branch-factor", text)
        self.assertIn(
            "--expected-branch-factor ${{ inputs.graph_branch_factor || '3' }}",
            text,
        )
        self.assertIn("scripts/measure_uncapped_feasible_items.py", text)
        self.assertIn("--item-scope all-visible", text)
        self.assertIn("--item-scope live-cap", text)
        self.assertIn("inputs.measurement_only == true", text)
        self.assertIn("inputs.measurement_only != true", text)
        self.assertIn("tests.test_attribute_placement_pybullet_e2e", text)
        self.assertIn("--post-shake-labels", text)

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
        self.assertIn("build_trajectory_advantage_dataset.py", text)
        self.assertIn("aggregate/trajectory-advantage", text)
        self.assertIn("rows_with_immediate_score_input", text)
        self.assertIn("evaluation_group_fold_consistent", text)
        self.assertIn("distributional_training_ready", text)
        self.assertIn("develop_post_shake_soft_reranker.py", text)
        self.assertIn("evaluate_frozen_post_shake_soft_reranker.py", text)
        self.assertIn("distributional_discovery.jsonl", text)
        self.assertIn("distributional_late_holdout.jsonl", text)
        self.assertIn("evaluate_prospective_phase_soft_policy.py", text)
        self.assertIn("phase-soft-policy-32351615182.json", text)
        self.assertIn("pip install -r requirements.txt", text)
        self.assertIn(
            "--policy reports/counterfactual-teacher-discovery/policy.json",
            text,
        )

    def test_h5_is_limited_to_three_known_root_level_ties(self):
        text = TIE_H5_WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("root_steps:"), 2)
        self.assertIn('root_steps: "6"', text)
        self.assertIn('root_steps: "6 9"', text)
        self.assertIn("--horizon 5", text)
        self.assertEqual(text.count("--expected-graphs 3"), 2)

    def test_branch_width_audit_is_limited_to_preregistered_h3_roots(self):
        text = BRANCH_WIDTH_WORKFLOW.read_text(encoding="utf-8")

        self.assertEqual(text.count("target:"), 4)
        self.assertIn("--steps 15", text)
        self.assertIn("--horizon 3", text)
        self.assertIn("--branch-factor 3", text)
        self.assertIn("--max-nodes 40", text)
        self.assertIn("--forced-candidate-spec", text)
        self.assertIn("--forced-target-id ${{ matrix.target }}", text)
        self.assertIn("compare_counterfactual_branch_width.py", text)
        self.assertIn("Enforce the preregistered stability gate", text)
        self.assertIn("if: steps.compare.outcome != 'success'", text)


if __name__ == "__main__":
    unittest.main()
