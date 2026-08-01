import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TaskARolloutWorkflowTests(unittest.TestCase):
    def test_workflow_freezes_screening_matrix_and_budgets(self):
        text = (
            ROOT / ".github" / "workflows" / "task-a-rollout-transfer.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('source_case: ["000", "001"]', text)
        self.assertIn("arm: [base, bounded128]", text)
        self.assertIn("repeat: [0, 1, 2]", text)
        self.assertIn("--offline-seconds 30", text)
        self.assertIn("--macro-seconds 0.5", text)
        self.assertIn("--optimization-timeout 40", text)


if __name__ == "__main__":
    unittest.main()
