import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SelfPlayPackingMctsWorkflowTests(unittest.TestCase):
    def test_workflow_runs_paired_physical_puct_and_renders_replays(self):
        text = (
            ROOT / ".github" / "workflows" / "self-play-packing-mcts.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", text)
        self.assertIn("push:", text)
        self.assertIn("experiment/counterfactual-graph", text)
        self.assertIn("tests.test_self_play_packing_search", text)
        self.assertIn("NEDO_REQUIRE_INTEGRATION", text)
        self.assertIn("--selection-mode rank0", text)
        self.assertIn("--selection-mode mcts", text)
        self.assertIn("--mcts-simulations", text)
        self.assertIn("inputs.simulations || '12'", text)
        self.assertIn("--mcts-horizon", text)
        self.assertIn("--mcts-prior uniform", text)
        self.assertIn("--mcts-temperature-drop-step 6", text)
        self.assertIn("evaluate_self_play_packing.py", text)
        self.assertIn("replays/mcts.html", text)
        self.assertIn("upload-artifact@v4", text)


if __name__ == "__main__":
    unittest.main()
