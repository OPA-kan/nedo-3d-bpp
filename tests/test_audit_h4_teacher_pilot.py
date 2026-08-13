from __future__ import annotations

import copy
import unittest

from scripts.audit_h4_teacher_pilot import audit
from tests.test_evaluate_counterfactual_afterstate_value import run


class H4TeacherPilotAuditTests(unittest.TestCase):
    def test_passes_twelve_unique_supported_signatures(self) -> None:
        fixture = run("h4")
        source = fixture["late"][0]
        rows = []
        for index in range(12):
            row = copy.deepcopy(source)
            row["teacher_id"] = f"teacher-{index}"
            row["lower_afterstate_tensor"]["packed_item_values"][0][0] += index
            label = row["continuation_labels"]["fill_score_proxy"]
            label["lower_continuation_values"] = [1.0, 2.0]
            label["higher_continuation_values"] = [2.0, 3.0]
            rows.append(row)
        fixture["late"] = rows
        report = audit(fixture)
        self.assertTrue(report["passed"])
        self.assertEqual(report["unique_directional_late_signatures"], 12)

    def test_fails_below_symmetric_support_coverage(self) -> None:
        fixture = run("h4")
        row = fixture["late"][0]
        label = row["continuation_labels"]["fill_score_proxy"]
        label["lower_continuation_values"] = [1.0]
        label["higher_continuation_values"] = [2.0, 3.0]
        report = audit(fixture)
        self.assertFalse(report["passed"])
        self.assertEqual(report["symmetric_support_coverage"], 0.0)


if __name__ == "__main__":
    unittest.main()
