from __future__ import annotations

import unittest

from scripts.test_task_a_risk_on_hypothesis import (
    analyze,
    exact_unpaired_permutation,
)


class TaskARiskOnHypothesisTests(unittest.TestCase):
    def test_complete_separation_exposes_three_by_three_resolution(self) -> None:
        result = exact_unpaired_permutation([1, 2, 3], [4, 5, 6])

        self.assertEqual(result["permutations"], 20)
        self.assertEqual(result["delta_risk_on_minus_default"], 3.0)
        self.assertEqual(result["p_improvement_one_sided"], 0.05)
        self.assertEqual(result["p_harm_one_sided"], 1.0)
        self.assertEqual(result["p_two_sided"], 0.1)
        self.assertEqual(result["minimum_one_sided_p"], 0.05)
        self.assertEqual(result["minimum_two_sided_p_without_ties"], 0.1)

    def test_primary_test_is_stratified_and_adoption_requires_no_regression(
        self,
    ) -> None:
        rows = []
        values = {
            "a000": {"default": [28, 29, 29], "risk_on": [23, 23, 22]},
            "a001": {"default": [19, 19, 19], "risk_on": [20, 20, 20]},
        }
        for source_case, arms in values.items():
            for arm, placed_values in arms.items():
                for repeat, placed in enumerate(placed_values):
                    rows.append(
                        {
                            "source_case": source_case,
                            "arm": arm,
                            "repeat": repeat,
                            "process_returncode": 0,
                            "placed_count": float(placed),
                            "fill_score": float(placed),
                            "offline_evaluations": float(placed),
                            "optimization_seconds": float(placed),
                        }
                    )

        result = analyze(rows)

        self.assertEqual(result["primary"]["observed_delta"], -2.5)
        self.assertEqual(result["primary"]["permutations"], 400)
        self.assertEqual(result["primary"]["p_improvement_one_sided"], 0.9525)
        self.assertEqual(result["primary"]["p_harm_one_sided"], 0.05)
        self.assertEqual(result["primary"]["p_two_sided"], 0.1)
        self.assertFalse(result["decision"]["no_regression_gate"])
        self.assertFalse(result["decision"]["adopt_risk_on"])

    def test_duplicate_execution_identity_is_rejected(self) -> None:
        row = {
            "source_case": "a000",
            "arm": "default",
            "repeat": 0,
            "process_returncode": 0,
            "placed_count": 1.0,
            "fill_score": 1.0,
            "offline_evaluations": 1.0,
            "optimization_seconds": 1.0,
        }
        other = dict(row, arm="risk_on")

        with self.assertRaisesRegex(ValueError, "duplicate observation"):
            analyze([row, dict(row), other])


if __name__ == "__main__":
    unittest.main()
