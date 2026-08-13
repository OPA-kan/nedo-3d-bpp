from __future__ import annotations

import copy
import unittest

from scripts.audit_counterfactual_afterstate_collection import audit
from tests.test_evaluate_counterfactual_afterstate_value import run


class CounterfactualAfterstateCollectionAuditTests(unittest.TestCase):
    def test_counts_model_visible_duplicates_across_runs(self) -> None:
        first = run("1")
        second = copy.deepcopy(first)
        second["run_id"] = "2"
        for split in ("discovery", "late"):
            for index, row in enumerate(second[split]):
                row["teacher_id"] = f"second-{split}-{index}"

        report = audit([first, second])

        late = report["splits"]["late"]
        self.assertEqual(late["directional_rows"], 2)
        self.assertEqual(late["unique_afterstate_signatures"], 1)
        self.assertEqual(late["rows_in_cross_run_duplicate_groups"], 2)
        self.assertFalse(report["development_independence_gate"]["passed"])

    def test_rejects_duplicate_run_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            audit([run("same"), run("same")])


if __name__ == "__main__":
    unittest.main()
