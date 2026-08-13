from __future__ import annotations

import unittest

from scripts.evaluate_frozen_fill_afterstate_policy import (
    aggregate_fallback_reports,
    evaluate_frozen,
)
from tests.test_evaluate_counterfactual_afterstate_value import run


class FrozenFillAfterstatePolicyTests(unittest.TestCase):
    def test_aggregates_preregistered_fallback_gate(self) -> None:
        policy = {
            "status": "frozen_awaiting_new_physical_run",
            "fallback_confirmation_gate": {
                "minimum_target_runs": 2,
                "require_no_target_run_regression": True,
                "maximum_pooled_exact_sign_p": 0.05,
            }
        }
        reports = [
            {
                "target_run_id": "a",
                "consensus_with_action_fallback": {
                    "rows": 10, "afterstate_rows": 8, "correct": 8,
                    "action_geometry_correct": 6,
                    "paired_vs_action_geometry": {
                        "wins": 4, "ties": 6, "losses": 0,
                    },
                },
            },
            {
                "target_run_id": "b",
                "consensus_with_action_fallback": {
                    "rows": 10, "afterstate_rows": 7, "correct": 8,
                    "action_geometry_correct": 6,
                    "paired_vs_action_geometry": {
                        "wins": 4, "ties": 6, "losses": 0,
                    },
                },
            },
        ]

        result = aggregate_fallback_reports(policy, reports)

        self.assertEqual(result["paired_vs_action_geometry"]["wins"], 8)
        self.assertEqual(result["paired_vs_action_geometry"]["losses"], 0)
        self.assertTrue(result["gate_passed"])

        policy["forbidden_confirmation_run_ids"] = ["a"]
        rejected = aggregate_fallback_reports(policy, reports)
        self.assertFalse(rejected["gate_passed"])
        self.assertFalse(
            rejected["gate_checks"]["eligible_confirmation_targets"]
        )

        policy["forbidden_confirmation_run_ids"] = []
        policy["fallback_confirmation_gate"]["required_target_run_ids"] = [
            "a", "c"
        ]
        wrong_targets = aggregate_fallback_reports(policy, reports)
        self.assertFalse(wrong_targets["gate_passed"])
        self.assertFalse(
            wrong_targets["gate_checks"]["exact_required_target_set"]
        )

    def test_evaluates_new_run_without_training_on_it(self) -> None:
        policy = {
            "status": "frozen_awaiting_new_physical_run",
            "confirmation_gate": {
                "minimum_coverage": 0.75,
                "maximum_errors": 0,
                "comparison": "no covered-row regression",
            },
        }
        report = evaluate_frozen(policy, [run("1"), run("2")], run("3"))

        self.assertEqual(report["training_run_ids"], ["1", "2"])
        self.assertEqual(report["target_run_id"], "3")
        self.assertTrue(report["gate_passed"])
        self.assertEqual(
            report["paired_consensus_vs_action_geometry"]["ties"], 1
        )

    def test_rejects_target_leakage(self) -> None:
        policy = {
            "status": "frozen_awaiting_new_physical_run",
            "confirmation_gate": {
                "minimum_coverage": 0.75, "maximum_errors": 0,
            },
        }
        with self.assertRaisesRegex(ValueError, "must not occur"):
            evaluate_frozen(policy, [run("same")], run("same"))

    def test_evaluates_distributional_label_family(self) -> None:
        policy = {
            "status": "frozen_awaiting_new_physical_run",
            "confirmation_gate": {
                "minimum_coverage": 0.75,
                "maximum_errors": 1,
            },
        }
        report = evaluate_frozen(
            policy, [run("1"), run("2")], run("3"),
            label_family="distributional_continuation_labels",
        )

        self.assertEqual(
            report["label_family"], "distributional_continuation_labels"
        )
        fallback = report["consensus_with_action_fallback"]
        self.assertEqual(fallback["rows"], 1)
        self.assertEqual(fallback["afterstate_rows"], 1)
        self.assertEqual(fallback["correct"], 1)
        self.assertEqual(
            fallback["paired_vs_action_geometry"], {
                "wins": 0,
                "ties": 1,
                "losses": 0,
                "exact_two_sided_sign_p": 1.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
