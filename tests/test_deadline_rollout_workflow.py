import pathlib
import unittest


class DeadlineRolloutWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path(
            ".github/workflows/deadline-rollout-shadow.yml"
        ).read_text(encoding="utf-8")

    def test_uses_frozen_truth_and_group_oof_allocator(self):
        self.assertIn("32763509936", self.text)
        self.assertIn("32796518151", self.text)
        self.assertIn("--candidate-budget 2", self.text)

    def test_alternate_arm_is_switchable_without_code_change(self):
        self.assertIn("allocator_artifact", self.text)
        self.assertIn("--alternate-mode", self.text)
        self.assertIn("ranker_next", self.text)

    def test_production_default_is_ranker_next_with_contested_deepening(self):
        self.assertIn('default: "ranker_next"', self.text)
        self.assertIn("--contested-extra-steps", self.text)
        self.assertIn('default: "6"', self.text)

    def test_enforces_ten_second_h3_shadow_without_value(self):
        self.assertIn("--decision-budget-seconds", self.text)
        self.assertIn("--max-continuation-steps 2", self.text)
        self.assertNotIn("leaf-eval value", self.text)

    def test_runs_all_twelve_cells(self):
        self.assertEqual(self.text.count("- {cell:"), 12)


if __name__ == "__main__":
    unittest.main()
