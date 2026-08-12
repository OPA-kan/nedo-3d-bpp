from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TaskARiskOnWorkflowTests(unittest.TestCase):
    def test_matrix_is_paired_on_two_cases_and_three_repeats(self):
        text = (
            ROOT / ".github" / "workflows" / "task-a-risk-on-proposal.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('source_case: ["000", "001"]', text)
        self.assertIn("arm: [default, risk_on]", text)
        self.assertIn("repeat: [0, 1, 2]", text)
        self.assertIn("--offline-seconds 150", text)
        self.assertIn("--optimization-timeout 180", text)
        self.assertIn('--source-case "a${{ matrix.source_case }}"', text)


if __name__ == "__main__":
    unittest.main()
