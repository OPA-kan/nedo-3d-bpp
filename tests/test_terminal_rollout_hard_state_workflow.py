import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "terminal-rollout-hard-state.yml"
)
SEASON_PLAN = ROOT / "reports" / "league" / "season" / "waves.json"


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

    def test_collects_stream_diverse_trajectories(self):
        # season waves grow the matrix; the cell count must always match
        # the aggregate guard and hold at least the 100-cell wave-4 base
        cells = re.findall(r"- cell: (\S+)", self.text)
        expected = int(
            re.search(r"--expected-manifests (\d+)", self.text).group(1)
        )
        self.assertEqual(len(cells), expected)
        self.assertEqual(len(cells), len(set(cells)))
        self.assertGreaterEqual(len(cells), 100)
        self.assertIn("dual-preloaded-dedicated-permute-000-17", cells)
        self.assertIn("dual-shelf-mixed-permute-001-43", cells)
        self.assertIn("single-preloaded-permute-000-89", cells)

    def test_league_eval_streams_never_enter_training(self):
        forbidden = json.loads(SEASON_PLAN.read_text(encoding="utf-8"))[
            "eval_variants_forbidden"
        ]
        self.assertEqual(len(forbidden), 7)
        for variant in forbidden:
            self.assertNotIn(f"stream: {variant}\n", self.text)

    def test_keeps_physics_as_oracle_and_builds_trigger_dataset(self):
        self.assertIn("NEDO_REQUIRE_INTEGRATION", self.text)
        self.assertIn("build_terminal_rollout_trigger_dataset.py", self.text)
        self.assertIn("trigger-dataset.json", self.text)


if __name__ == "__main__":
    unittest.main()
