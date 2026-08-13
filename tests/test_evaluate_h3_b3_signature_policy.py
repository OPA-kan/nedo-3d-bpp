from __future__ import annotations

import copy
import unittest

from scripts.evaluate_h3_b3_signature_policy import (
    _deduplicate,
    _has_symmetric_continuation_support,
)
from tests.test_evaluate_counterfactual_afterstate_value import run


class H3B3SignaturePolicyTests(unittest.TestCase):
    def test_consistent_duplicate_is_collapsed(self) -> None:
        row = run("x")["discovery"][0]
        duplicate = copy.deepcopy(row)
        duplicate["teacher_id"] = "duplicate"
        self.assertEqual(len(_deduplicate([row, duplicate])), 1)

    def test_conflicting_duplicate_is_rejected(self) -> None:
        row = run("x")["discovery"][0]
        duplicate = copy.deepcopy(row)
        label = duplicate["continuation_labels"]["fill_score_proxy"]
        label["relation"] = (
            "lower_afterstate_better"
            if label["relation"] == "higher_afterstate_better"
            else "higher_afterstate_better"
        )
        with self.assertRaisesRegex(ValueError, "conflicting relations"):
            _deduplicate([row, duplicate])

    def test_symmetric_support_requires_both_sides(self) -> None:
        row = run("x")["discovery"][0]
        label = row["continuation_labels"]["fill_score_proxy"]
        label["lower_continuation_values"] = [1.0, 2.0]
        label["higher_continuation_values"] = [1.0]
        self.assertFalse(_has_symmetric_continuation_support(row))
        label["higher_continuation_values"].append(2.0)
        self.assertTrue(_has_symmetric_continuation_support(row))


if __name__ == "__main__":
    unittest.main()
