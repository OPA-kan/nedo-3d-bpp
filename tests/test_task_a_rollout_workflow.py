import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TaskARolloutWorkflowTests(unittest.TestCase):
    def test_workflow_freezes_adoption_matrix_and_budgets(self):
        text = (
            ROOT / ".github" / "workflows" / "task-a-rollout-transfer.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('source_case: ["000"]', text)
        self.assertIn("repeat: [0, 1, 2]", text)
        self.assertIn("--offline-seconds 150", text)
        self.assertIn("--macro-seconds 0.5", text)
        self.assertIn("--optimization-timeout 180", text)

    def test_matrix_contrasts_the_shipped_path_against_legacy(self):
        """
        Post-ADR-002 the treatment arm is the shipped default, so the
        matrix measures `default` (nothing set, exactly what a submission
        runs) rather than `bounded128` (the same values, but forced). A
        matrix of only bounded arms would never exercise the default.
        """
        text = (
            ROOT / ".github" / "workflows" / "task-a-rollout-transfer.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("arm: [base, default]", text)


if __name__ == "__main__":
    unittest.main()
