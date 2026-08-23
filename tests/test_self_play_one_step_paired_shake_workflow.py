import pathlib
import unittest


class OneStepPairedShakeWorkflowTests(unittest.TestCase):
    def test_workflow_freezes_root_action_pair_and_runs_no_continuation(self):
        path = pathlib.Path(
            ".github/workflows/self-play-one-step-paired-shake.yml"
        )
        text = path.read_text(encoding="utf-8")

        self.assertIn("evaluate_one_step_paired_shake.py", text)
        self.assertIn("baseline_convergence_run_id", text)
        self.assertIn("rescue_convergence_run_id", text)
        self.assertIn("--expected-pairs", text)
        self.assertIn("tests.test_postshake_capture", text)
        self.assertNotIn("progressive", text.lower())


if __name__ == "__main__":
    unittest.main()
