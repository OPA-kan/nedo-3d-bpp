from __future__ import annotations

import pathlib
import unittest


WORKFLOW = (
    pathlib.Path(__file__).parents[1]
    / ".github" / "workflows" / "late-item-cap-confirmation.yml"
)


class LateItemCapConfirmationWorkflowTests(unittest.TestCase):
    def test_uses_fresh_paired_permutations_without_holdout(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('source_case: ["000", "001"]', text)
        self.assertIn("--seed 20260813", text)
        self.assertIn("--variants 8", text)
        self.assertIn("--mode permute", text)
        self.assertIn("--look-ahead 15", text)
        self.assertIn("--arm late_narrow_pool_cap16", text)
        self.assertIn("scripts/run_stream_paired.py", text)
        self.assertNotIn("--open-final-holdout", text)


if __name__ == "__main__":
    unittest.main()
