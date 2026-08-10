import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "multi-axis-selector-shadow.yml"
)


class MultiAxisSelectorWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_matrix_has_controls_shadow_and_three_repeats(self):
        self.assertIn(
            "arm: [base, base_null, multi_axis_shadow, multi_axis_enforce]",
            self.text,
        )
        self.assertIn("repeat: [0, 1, 2]", self.text)
        self.assertEqual(self.text.count("case_id:"), 5)

    def test_aggregate_persists_full_vector_and_noise_floor(self):
        self.assertIn("--summarize", self.text)
        self.assertIn("scripts/summarize_ablation.py", self.text)
        self.assertIn("noise-floor.json", self.text)
        self.assertIn("summary.json", self.text)


if __name__ == "__main__":
    unittest.main()
