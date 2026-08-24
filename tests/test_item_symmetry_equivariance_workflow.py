import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "item-symmetry-equivariance.yml"


class ItemSymmetryEquivarianceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_real_physics_and_non_skip_contract_are_required(self):
        self.assertIn("requirements-simulator.txt", self.text)
        self.assertIn('NEDO_REQUIRE_INTEGRATION: "1"', self.text)
        self.assertIn("audit_item_symmetry_equivariance.py", self.text)

    def test_all_six_single_agent_cells_are_audited(self):
        for cell in (
            "dual-empty-original",
            "dual-preloaded-dedicated-source-001",
            "dual-shelf-mixed-source-001",
            "single-empty-noshelf-original",
            "single-empty-shelf-original",
            "single-preloaded-original",
        ):
            self.assertIn(f"cell: {cell}", self.text)

    def test_aggregate_enforces_six_nonvacuous_cells(self):
        self.assertIn("needs: symmetry-cell", self.text)
        self.assertIn("aggregate_item_symmetry_equivariance.py", self.text)
        self.assertIn("--expected-cells 6", self.text)


if __name__ == "__main__":
    unittest.main()
