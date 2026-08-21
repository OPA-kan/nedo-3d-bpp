import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SelfPlayPackingWorkflowTests(unittest.TestCase):
    def test_workflow_runs_symmetric_control_and_exploration(self):
        text = (
            ROOT / ".github" / "workflows" / "self-play-packing-game.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("experiment/counterfactual-graph", text)
        self.assertIn("tests.test_attribute_placement_pybullet_e2e", text)
        self.assertIn("--minimum-block 3", text)
        self.assertIn("--handoff-probability", text)
        self.assertIn("--selection-mode rank0", text)
        self.assertIn("--selection-mode temperature", text)
        self.assertIn("--episodes 2", text)
        self.assertIn("--episodes 4", text)
        self.assertIn("evaluate_self_play_packing.py", text)
        self.assertIn("render_self_play_replay.py", text)
        self.assertIn("temperature-game-$game.html", text)
        self.assertIn("-eq 6", text)
        self.assertIn("upload-artifact@v4", text)


if __name__ == "__main__":
    unittest.main()
