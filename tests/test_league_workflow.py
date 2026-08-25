import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "league-match.yml"
TRAINING_STREAMS = (
    # every stream used by the hard-state training waves must stay out
    # of the frozen eval set
    "permute-000-17", "permute-000-29", "permute-000-41", "permute-000-53",
    "permute-000-61", "permute-000-71", "permute-000-79", "permute-000-89",
    "permute-000-97", "permute-000-103", "permute-000-109",
    "permute-000-127", "permute-000-137", "permute-000-151",
    "permute-000-157", "permute-000-163", "permute-000-167",
    "permute-000-173", "permute-000-179", "permute-000-181",
    "permute-001-23", "permute-001-31", "permute-001-43", "permute-001-59",
    "permute-001-67", "permute-001-73", "permute-001-83", "permute-001-101",
    "permute-001-107", "permute-001-113", "permute-001-127",
    "permute-001-139", "permute-001-149", "permute-001-151",
    "permute-001-157", "permute-001-163",
)


class LeagueWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_ten_frozen_eval_episodes(self):
        self.assertEqual(self.text.count("- {cell:"), 10)
        self.assertIn("evaluate_league.py", self.text)
        self.assertIn("reports/league/registry.json", self.text)

    def test_eval_streams_are_held_out_from_training_waves(self):
        for stream in TRAINING_STREAMS:
            self.assertNotIn(f"stream: {stream}}}", self.text)

    def test_policy_model_only_reaches_the_learned_arms(self):
        # the policy model is a distilled selection head; V stays banned,
        # and even the policy model is attached only when the learned or
        # online arm is explicitly requested
        self.assertEqual(self.text.count("--model-dir"), 1)
        self.assertIn(
            'if [ "$policy" = "learned" ] || [ "$policy" = "online" ]; then',
            self.text,
        )
        self.assertIn(
            'model_flags="--model-dir reports/league/model"', self.text
        )
        self.assertEqual(self.text.count(
            'contains(fromJSON(\'["learned","online"]\'),'
            " inputs.policy || 'legacy')"
        ), 2)
        self.assertIn("requirements-learning.txt", self.text)

    def test_exhibition_mode_reports_without_promoting(self):
        # SLA-exempt arms (online clones, rule studs) get a full paired
        # report but can never touch the registry
        self.assertIn('exhibition) flags="--exhibition" ;;', self.text)
        self.assertNotIn('exhibition) flags="--promote-on-pass"', self.text)

    def test_frozen_settings(self):
        self.assertIn("--environment-seed 42", self.text)
        self.assertIn("--max-steps 40", self.text)
        self.assertIn("--rollout-max-steps 40", self.text)

    def test_push_bootstraps_or_audits_the_anchor_only(self):
        self.assertIn("push:", self.text)
        self.assertIn("- .github/workflows/league-match.yml", self.text)
        self.assertIn('mode="bootstrap"; name="pi0-legacy"', self.text)
        self.assertIn('mode="audit"; name="pi0-legacy"', self.text)


if __name__ == "__main__":
    unittest.main()
