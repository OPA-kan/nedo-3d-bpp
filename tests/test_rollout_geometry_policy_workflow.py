import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class RolloutGeometryPolicyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (
            ROOT / ".github" / "workflows"
            / "rollout-geometry-policy-learning.yml"
        ).read_text(encoding="utf-8")
        cls.collection = (
            ROOT / ".github" / "workflows"
            / "terminal-rollout-hard-state.yml"
        ).read_text(encoding="utf-8")

    def test_recovery_matrix_mirrors_the_collection_matrix(self):
        # season waves keep both matrices in lockstep: every collected
        # cell is recovered before training, and the guard agrees
        learning_cells = re.findall(r"- \{cell: ([^,]+),", self.text)
        collection_cells = re.findall(r"- cell: (\S+)", self.collection)
        self.assertEqual(sorted(learning_cells), sorted(collection_cells))
        expected = int(
            re.search(r"--expected-cells (\d+)", self.text).group(1)
        )
        self.assertEqual(len(learning_cells), expected)
        self.assertIn("needs: recover-actions", self.text)

    def test_policy_excludes_h1_inputs(self):
        self.assertIn("--candidate-feature-mode geometry", self.text)
        self.assertIn("H1 physical outcomes used as input: no", self.text)

    def test_mainline_objective_is_incumbent_preference(self):
        # design review 2026-08-25: behavior cloning collapses to the
        # incumbent; the deployable head learns P(alternate beats
        # incumbent) from terminal dominance instead
        self.assertIn("--objective preference", self.text)

    def test_freezes_the_deployable_ensemble_for_the_league(self):
        self.assertIn(
            "--save-model-dir reports/geometry-policy/model", self.text
        )
        self.assertIn("name: rollout-policy-model", self.text)
        self.assertIn("path: reports/geometry-policy/model/", self.text)

    def test_season_runs_are_dispatch_only_with_group_oof(self):
        # a push against a stale default source would train a mismatched
        # matrix mid-season, so the workflow only runs when dispatched
        # with an explicit fresh aggregate
        self.assertNotIn("push:", self.text)
        self.assertIn("source_run_id", self.text)
        self.assertIn("--folds 4", self.text)
        self.assertIn("--repeats 3", self.text)

    def test_successful_season_training_dispatches_title_match(self):
        self.assertIn("continue-season:", self.text)
        self.assertIn("league_season.py identity", self.text)
        self.assertIn("gh workflow run league-match.yml", self.text)
        self.assertIn('-f model_run_id="$GITHUB_RUN_ID"', self.text)


if __name__ == "__main__":
    unittest.main()
