import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SelfPlayPackingMatrixWorkflowTests(unittest.TestCase):
    def test_workflow_covers_representative_scenarios_and_selects_replays(self):
        text = (
            ROOT / ".github" / "workflows" / "self-play-packing-matrix.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("experiment/counterfactual-graph", text)
        for scenario in (
            "single-empty-noshelf",
            "single-empty-shelf",
            "dual-shelf-mixed",
            "dual-preloaded-dedicated",
        ):
            self.assertIn(scenario, text)
        self.assertIn("--selection-mode rank0", text)
        self.assertIn("--selection-mode temperature", text)
        self.assertIn("select_critical_self_play_replays.py", text)
        self.assertIn("--top-k 6", text)
        self.assertEqual(text.count("actions/download-artifact@v4"), 4)
        self.assertIn("critical/index.html", text)
        self.assertIn("upload-artifact@v4", text)


if __name__ == "__main__":
    unittest.main()
