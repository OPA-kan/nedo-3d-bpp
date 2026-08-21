import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PairedSearchFollowWorkflowTests(unittest.TestCase):
    def test_workflow_builds_stability_views_before_fresh_pair(self):
        text = (
            ROOT / ".github" / "workflows"
            / "counterfactual-graph-paired-search-follow.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("build_view h3-b3 3 3", text)
        self.assertIn("build_view h4-b3 4 3", text)
        self.assertIn("build_view h3-b4 3 4", text)
        self.assertIn("--require-horizon 4", text)
        self.assertIn("--require-branch-factor 4", text)
        self.assertIn("build_paired_search_follow.py", text)
        self.assertIn("evaluate_paired_search_follow.py", text)


if __name__ == "__main__":
    unittest.main()
