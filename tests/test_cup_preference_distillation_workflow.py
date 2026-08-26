import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class CupPreferenceDistillationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (
            ROOT / ".github" / "workflows"
            / "cup-preference-distillation.yml"
        ).read_text(encoding="utf-8")

    def test_requires_explicit_preregistered_sources(self):
        for value in (
            "cup_run_id:", "cup_id:", "base_model_run_id:",
            "expected_pairs:",
        ):
            self.assertIn(value, self.text)
        self.assertIn('pattern: cup-cell-*', self.text)
        self.assertIn('name: rollout-policy-model', self.text)

    def test_builds_then_distils_without_auto_challenge(self):
        self.assertIn("build_cup_preference_dataset.py", self.text)
        self.assertIn("distill_persistent_preference_memory.py", self.text)
        self.assertIn("name: shun-long-policy-model", self.text)
        self.assertNotIn("league-match.yml", self.text)
        self.assertNotIn("--promote", self.text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.text)

    def test_freezes_cup003_online_adapter_hyperparameters(self):
        self.assertIn("--learning-rate 0.05", self.text)
        self.assertIn("--update-steps 2", self.text)
        self.assertIn("--trust-radius 1.0", self.text)

    def test_installs_runtime_and_learning_dependencies(self):
        self.assertIn(
            "pip install -r requirements.txt -r requirements-learning.txt",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
