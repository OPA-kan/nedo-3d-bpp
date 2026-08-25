import pathlib
import unittest


class RolloutGeometryPolicyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path(
            ".github/workflows/rollout-geometry-policy-learning.yml"
        ).read_text(encoding="utf-8")

    def test_recovers_all_cells_before_training(self):
        # generation 0 trains on the full 100-cell wave-4 corpus
        self.assertEqual(self.text.count("- {cell:"), 100)
        self.assertIn("needs: recover-actions", self.text)
        self.assertIn("--expected-cells 100", self.text)

    def test_policy_excludes_h1_inputs(self):
        self.assertIn("--candidate-feature-mode geometry", self.text)
        self.assertIn("H1 physical outcomes used as input: no", self.text)

    def test_freezes_the_deployable_ensemble_for_the_league(self):
        self.assertIn(
            "--save-model-dir reports/geometry-policy/model", self.text
        )
        self.assertIn("name: rollout-policy-model", self.text)
        self.assertIn("path: reports/geometry-policy/model/", self.text)

    def test_search_teacher_is_frozen_and_group_oof(self):
        # wave-4 aggregate (100 cells) is the frozen teacher
        self.assertIn("32822842633", self.text)
        self.assertIn("--folds 4", self.text)
        self.assertIn("--repeats 3", self.text)


if __name__ == "__main__":
    unittest.main()
