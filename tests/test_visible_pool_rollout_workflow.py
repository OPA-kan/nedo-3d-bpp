import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "visible-pool-rollout-ablation.yml"


class VisiblePoolRolloutWorkflowTests(unittest.TestCase):
    def test_enforce_matrix_covers_requested_eight_cases_and_three_repeats(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("arm: [base, rollout_enforce]", text)
        self.assertIn("repeat: [0, 1, 2]", text)
        for case_id in (
            "b000-k10",
            "b000-k15",
            "b000-k20",
            "b000-k40",
            "b001-k10",
            "b001-k20",
            "b001-k30",
            "b001-k40",
        ):
            self.assertIn(f"case_id: {case_id}", text)
        self.assertIn("--open-final-holdout", text)


if __name__ == "__main__":
    unittest.main()
