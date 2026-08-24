import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "terminal-rollout-hard-state.yml"
)


class TerminalRolloutHardStateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_has_scoped_bootstrap_and_is_v_free(self):
        self.assertIn("workflow_dispatch", self.text)
        self.assertIn("push:", self.text)
        self.assertIn(
            "- .github/workflows/terminal-rollout-hard-state.yml",
            self.text,
        )
        self.assertNotIn("- scripts/run_terminal_rollout_policy.py", self.text)
        self.assertLess(
            self.text.index("      rollout_max_steps:"),
            self.text.index("  # A workflow_dispatch file"),
        )
        self.assertEqual(self.text.count("--policy terminal-rollout"), 1)
        self.assertNotIn("--model-dir", self.text)

    def test_collects_twelve_stream_diverse_trajectories(self):
        self.assertEqual(self.text.count("          - cell:"), 12)
        self.assertIn("dual-preloaded-dedicated-permute-000-17", self.text)
        self.assertIn("dual-shelf-mixed-permute-001-43", self.text)
        self.assertIn("single-preloaded-permute-000-89", self.text)
        self.assertIn("--expected-manifests 12", self.text)

    def test_keeps_physics_as_oracle_and_builds_trigger_dataset(self):
        self.assertIn("NEDO_REQUIRE_INTEGRATION", self.text)
        self.assertIn("build_terminal_rollout_trigger_dataset.py", self.text)
        self.assertIn("trigger-dataset.json", self.text)


if __name__ == "__main__":
    unittest.main()
