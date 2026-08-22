import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SelfPlayPuctConvergenceWorkflowTests(unittest.TestCase):
    def test_workflow_downloads_source_and_shards_targeted_reruns(self):
        text = (
            ROOT / ".github" / "workflows"
            / "self-play-puct-convergence.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("source_run_id", text)
        self.assertIn("experiment/counterfactual-graph", text)
        self.assertIn("inputs.source_run_id || '32515349437'", text)
        self.assertIn("[skip convergence]", text)
        self.assertIn("actions: read", text)
        self.assertIn("gh run download", text)
        self.assertIn("self-play-puct-matrix-aggregate-", text)
        self.assertIn("rerun_self_play_puct_roots.py", text)
        self.assertIn("shard_index", text)
        self.assertIn("evaluate_self_play_puct_convergence.py", text)
        self.assertIn("--expected-roots 58", text)
        self.assertIn("--candidate-audit-limit 64", text)
        self.assertIn("candidate_rescue_limit", text)
        self.assertIn("--candidate-rescue-limit", text)
        self.assertIn("baseline_convergence_run_id", text)
        self.assertIn("compare_self_play_puct_rescue.py", text)
        self.assertIn("evaluate_adaptive_puct_schedule.py", text)
        self.assertIn("rescue-comparison.md", text)
        self.assertIn("rescue_candidates_searchable", (
            ROOT / "scripts" / "rerun_self_play_puct_roots.py"
        ).read_text(encoding="utf-8"))
        self.assertIn(
            "(inputs.candidate_rescue_limit || '0') != '0'", text
        )


if __name__ == "__main__":
    unittest.main()
