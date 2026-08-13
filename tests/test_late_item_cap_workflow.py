from __future__ import annotations

import pathlib
import unittest


WORKFLOW = (
    pathlib.Path(__file__).parents[1]
    / ".github" / "workflows" / "late-item-cap-ablation.yml"
)


class LateItemCapWorkflowTests(unittest.TestCase):
    def test_fresh_development_matrix_is_paired_and_excludes_holdout(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("arm: [base, late_item_cap20]", text)
        self.assertIn("replicate: [0, 1, 2]", text)
        for case_id in (
            "b000-k15", "b000-k20", "b000-k40", "b001-k20", "b001-k30",
        ):
            self.assertIn(f"case_id: {case_id}", text)
        self.assertNotIn("b001-k40", text)
        self.assertNotIn("b001-k10", text)
        self.assertNotIn("--open-final-holdout", text)


if __name__ == "__main__":
    unittest.main()
