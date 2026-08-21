import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "residual-affordance-shadow.yml"
ROUTER = ROOT / ".github" / "workflows" / "multi-axis-selector-shadow.yml"


class ResidualAffordanceShadowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_wave_is_shadow_only_with_paired_controls(self):
        self.assertIn(
            "arm: [base, residual_affordance_shadow]", self.text
        )
        self.assertNotIn("residual_affordance_enforce", self.text)
        self.assertIn("repeat: [0, 1, 2]", self.text)
        self.assertEqual(self.text.count("case_id:"), 5)

    def test_aggregate_keeps_trace_reach_and_noise_floor(self):
        self.assertIn("--summarize", self.text)
        self.assertIn("scripts/summarize_ablation.py", self.text)
        self.assertIn("summary.json", self.text)
        self.assertIn("noise-floor.json", self.text)
        self.assertIn(
            "scripts/evaluate_residual_affordance_shadow_gate_v3.py",
            self.text,
        )
        for run_id in ("32380902237", "32381957502", "32435231411"):
            self.assertIn(run_id, self.text)
        self.assertIn("gate-v3.json", self.text)
        self.assertIn("gate-v3.md", self.text)

    def test_existing_default_branch_workflow_routes_to_new_wave(self):
        self.assertIn("wave:", self.router)
        self.assertIn("- residual_affordance", self.router)
        self.assertIn(
            "uses: ./.github/workflows/residual-affordance-shadow.yml",
            self.router,
        )
        self.assertIn("workflow_call:", self.text)


if __name__ == "__main__":
    unittest.main()
