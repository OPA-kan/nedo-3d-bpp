from __future__ import annotations

import unittest

from scripts.evaluate_frozen_fill_afterstate_policy import evaluate_frozen
from tests.test_evaluate_counterfactual_afterstate_value import run


class FrozenFillAfterstatePolicyTests(unittest.TestCase):
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

    def test_rejects_target_leakage(self) -> None:
        policy = {
            "status": "frozen_awaiting_new_physical_run",
            "confirmation_gate": {
                "minimum_coverage": 0.75, "maximum_errors": 0,
            },
        }
        with self.assertRaisesRegex(ValueError, "must not occur"):
            evaluate_frozen(policy, [run("same")], run("same"))


if __name__ == "__main__":
    unittest.main()
