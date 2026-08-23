import pathlib
import unittest


class SelfPlayValueShadowWorkflowTests(unittest.TestCase):
    def test_freezes_support_and_separates_training_from_shadow(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow = (
            root / ".github" / "workflows" / "self-play-value-shadow.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("value_run_id:", workflow)
        self.assertIn("reference_run_id:", workflow)
        self.assertIn("scripts/evaluate_self_play_value_shadow.py", workflow)
        self.assertIn("scripts/aggregate_self_play_value_shadow.py", workflow)
        self.assertNotIn("progressive-widening", workflow)
        self.assertNotIn("policy-head", workflow)


if __name__ == "__main__":
    unittest.main()
