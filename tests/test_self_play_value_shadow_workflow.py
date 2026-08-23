import pathlib
import subprocess
import sys
import unittest


class SelfPlayValueShadowWorkflowTests(unittest.TestCase):
    def test_aggregate_script_can_be_invoked_by_path(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/aggregate_self_play_value_shadow.py", "--help"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_freezes_support_and_separates_training_from_shadow(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow = (
            root / ".github" / "workflows" / "self-play-value-shadow.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("value_run_id:", workflow)
        self.assertIn("reference_run_id:", workflow)
        self.assertIn("scripts/evaluate_self_play_value_shadow.py", workflow)
        self.assertIn("scripts/aggregate_self_play_value_shadow.py", workflow)
        self.assertNotIn("progressive-widening", workflow)
        self.assertNotIn("policy-head", workflow)

    def test_registered_convergence_gateway_exposes_all_three_stages(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow = (
            root / ".github" / "workflows" / "self-play-puct-convergence.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("inputs.experiment == 'value'", workflow)
        self.assertIn("inputs.experiment == 'shake'", workflow)
        self.assertIn("inputs.experiment == 'shadow'", workflow)
        self.assertIn("group-excluded ensemble V", workflow)
        self.assertIn("scripts/evaluate_one_step_paired_shake.py", workflow)
        self.assertIn("scripts/evaluate_self_play_value_shadow.py", workflow)


if __name__ == "__main__":
    unittest.main()
