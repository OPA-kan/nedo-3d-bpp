import pathlib
import unittest


class SelfPlaySetValueWorkflowTests(unittest.TestCase):
    def test_trains_behavior_value_ensemble_without_policy_or_widening(self):
        text = pathlib.Path(
            ".github/workflows/self-play-set-value.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("build_self_play_pv_dataset.py", text)
        self.assertIn("train_self_play_set_value.py", text)
        self.assertIn("requirements-learning.txt", text)
        self.assertIn("ensemble_size", text)
        self.assertNotIn("policy-bootstrap", text)
        self.assertNotIn("progressive", text.lower())


if __name__ == "__main__":
    unittest.main()
