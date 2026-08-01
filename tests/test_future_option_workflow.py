from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "future-option-ablation.yml"


class FutureOptionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_paired_arms_on_all_five_development_configs(self):
        for case_id in (
            "b000-k15",
            "b000-k20",
            "b000-k40",
            "b001-k20",
            "b001-k30",
        ):
            self.assertEqual(self.text.count(f"case_id: {case_id}"), 2)
        self.assertEqual(self.text.count("arm: base"), 5)
        self.assertEqual(self.text.count("arm: future-option"), 5)

    def test_compact_aggregate_is_committed_but_raw_runs_are_artifacts(self):
        self.assertIn("reports/future-option/history/${{ github.run_id }}", self.text)
        self.assertIn("actions/upload-artifact@v4", self.text)
        self.assertNotIn("git add reports/future-option-guard-results", self.text)


if __name__ == "__main__":
    unittest.main()
