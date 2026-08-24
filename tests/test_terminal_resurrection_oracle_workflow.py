import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "terminal-resurrection-oracle.yml"


class TerminalResurrectionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_paired_v0_and_puct_without_oracle_allocation(self):
        self.assertEqual(self.text.count("--leaf-eval measured"), 2)
        self.assertNotIn("--leaf-eval rollout", self.text)
        self.assertEqual(self.text.count("--terminal-audit"), 2)
        self.assertIn("--allocation frontier", self.text)
        self.assertIn("--allocation pareto-puct", self.text)
        self.assertIn('environment-seed 42', self.text)

    def test_uses_all_six_preregistered_phase4_cells(self):
        for cell in (
            "dual-empty-original",
            "dual-preloaded-dedicated-source-001",
            "dual-shelf-mixed-source-001",
            "single-empty-noshelf-original",
            "single-empty-shelf-original",
            "single-preloaded-original",
        ):
            self.assertIn(f"cell: {cell}", self.text)

    def test_aggregate_is_required_to_validate_pair_identity(self):
        self.assertIn("needs: paired-cell", self.text)
        self.assertIn("aggregate_terminal_resurrection_oracle.py", self.text)
        self.assertIn("--expected-cells 6", self.text)


if __name__ == "__main__":
    unittest.main()
