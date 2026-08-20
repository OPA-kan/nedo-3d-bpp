import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "residual-affordance-shadow.yml"


class ResidualAffordanceShadowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
