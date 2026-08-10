import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "structured-selector-negative-control.yml"
)


class StructuredSelectorWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_matrix_has_two_controls_treatment_and_three_repeats(self):
        self.assertIn("arm: [base, base_null, structured_noop]", self.text)
        self.assertIn("repeat: [0, 1, 2]", self.text)
        self.assertEqual(self.text.count("case_id:"), 5)

    def test_aggregate_uses_full_vector_and_noise_floor_reports(self):
        self.assertIn("--summarize", self.text)
        self.assertIn("scripts/summarize_ablation.py", self.text)
        self.assertIn("noise-floor.json", self.text)
        self.assertIn("summary.json", self.text)


if __name__ == "__main__":
    unittest.main()
