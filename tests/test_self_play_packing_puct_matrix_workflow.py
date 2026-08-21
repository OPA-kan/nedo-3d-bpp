import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SelfPlayPackingPuctMatrixWorkflowTests(unittest.TestCase):
    def test_workflow_runs_paired_scenario_stream_matrix_and_aggregates(self):
        text = (
            ROOT / ".github" / "workflows"
            / "self-play-packing-puct-matrix.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", text)
        self.assertIn("experiment/counterfactual-graph", text)
        for scenario in (
            "single-empty-noshelf", "single-empty-shelf",
            "dual-shelf-mixed", "dual-preloaded-dedicated",
        ):
            self.assertIn(f"- {scenario}", text)
        self.assertIn("- original", text)
        self.assertIn("- permute-000-17", text)
        self.assertIn("--environment-seed 42", text)
        self.assertIn("--selection-mode rank0", text)
        self.assertIn("--selection-mode mcts", text)
        self.assertIn("--mcts-simulations 12", text)
        self.assertIn("--mcts-horizon 2", text)
        self.assertIn("--mcts-temperature-drop-step 6", text)
        self.assertIn("merge-multiple: true", text)
        self.assertIn("evaluate_self_play_puct_matrix.py", text)
        self.assertIn("replays/mcts.html", text)
        self.assertIn("upload-artifact@v4", text)


if __name__ == "__main__":
    unittest.main()
