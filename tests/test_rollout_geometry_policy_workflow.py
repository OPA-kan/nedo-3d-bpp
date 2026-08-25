import pathlib
import unittest


class RolloutGeometryPolicyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path(
            ".github/workflows/rollout-geometry-policy-learning.yml"
        ).read_text(encoding="utf-8")

    def test_recovers_all_cells_before_training(self):
        self.assertEqual(self.text.count("- {cell:"), 36)
        self.assertIn("needs: recover-actions", self.text)
        self.assertIn("--expected-cells 36", self.text)

    def test_policy_excludes_h1_inputs(self):
        self.assertIn("--candidate-feature-mode geometry", self.text)
        self.assertIn("H1 physical outcomes used as input: no", self.text)

    def test_search_teacher_is_frozen_and_group_oof(self):
        # wave-3 aggregate (36 cells) is the frozen teacher
        self.assertIn("32813542943", self.text)
        self.assertIn("--folds 4", self.text)
        self.assertIn("--repeats 3", self.text)


if __name__ == "__main__":
    unittest.main()
