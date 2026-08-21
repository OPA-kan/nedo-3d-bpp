import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "residual-affordance-enforce-canary.yml"
ROUTER = ROOT / ".github" / "workflows" / "multi-axis-selector-shadow.yml"


class ResidualAffordanceEnforceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_canary_is_paired_and_replicated(self):
        self.assertIn("arm: [base, residual_affordance_enforce]", self.text)
        self.assertIn("repeat: [0, 1, 2]", self.text)
        self.assertEqual(self.text.count("case_id:"), 5)

    def test_gate_is_persisted_before_it_is_enforced(self):
        self.assertIn(
            "scripts/evaluate_residual_affordance_enforce_canary.py",
            self.text,
        )
        self.assertLess(
            self.text.index("Persist compact canary history"),
            self.text.index("Enforce preregistered canary gate"),
        )
        self.assertIn("gate.json", self.text)
        self.assertIn("gate.md", self.text)

    def test_router_exposes_canary_without_changing_shadow_wave(self):
        self.assertIn("- residual_affordance_enforce", self.router)
        self.assertIn(
            "uses: ./.github/workflows/residual-affordance-enforce-canary.yml",
            self.router,
        )


if __name__ == "__main__":
    unittest.main()
