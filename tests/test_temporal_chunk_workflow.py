import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "temporal-chunk-ensemble-ablation.yml"
)
STRIDE4_WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "temporal-chunk-stride4-ablation.yml"
)


class TemporalChunkWorkflowTests(unittest.TestCase):
    def test_shadow_matrix_is_paired_and_uses_three_repeats(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("arm: [base, temporal_chunk_shadow]", text)
        self.assertIn("repeat: [0, 1, 2]", text)
        for case_id in (
            "b000-k15",
            "b000-k20",
            "b000-k40",
            "b001-k20",
            "b001-k30",
        ):
            self.assertIn(f"case_id: {case_id}", text)
        self.assertNotIn("--open-final-holdout", text)

    def test_compact_history_is_persisted_by_run_id(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("permissions:\n      contents: write", text)
        self.assertIn(
            "reports/temporal-chunk/history/${{ github.run_id }}", text
        )
        self.assertIn("git push origin \"HEAD:$GITHUB_REF_NAME\"", text)

    def test_stride4_control_is_paired_and_uses_the_same_cases(self):
        text = STRIDE4_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            "arm: [base, temporal_chunk_shadow_stride4]", text
        )
        self.assertIn("repeat: [0, 1, 2]", text)
        for case_id in (
            "b000-k15",
            "b000-k20",
            "b000-k40",
            "b001-k20",
            "b001-k30",
        ):
            self.assertIn(f"case_id: {case_id}", text)
        self.assertNotIn("--open-final-holdout", text)

    def test_stride4_control_persists_compact_history(self):
        text = STRIDE4_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("permissions:\n      contents: write", text)
        self.assertIn(
            "reports/temporal-chunk/history/${{ github.run_id }}", text
        )
        self.assertIn("git push origin \"HEAD:$GITHUB_REF_NAME\"", text)


if __name__ == "__main__":
    unittest.main()
