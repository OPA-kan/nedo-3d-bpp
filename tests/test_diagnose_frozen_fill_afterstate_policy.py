from __future__ import annotations

import unittest

import numpy as np

from scripts.diagnose_frozen_fill_afterstate_policy import (
    _distance_context,
    diagnose,
)
from scripts.evaluate_counterfactual_afterstate_value import _eligible
from scripts.evaluate_frozen_fill_afterstate_policy import evaluate_frozen
from tests.test_evaluate_counterfactual_afterstate_value import run


class FrozenFillAfterstateDiagnosisTests(unittest.TestCase):
    def test_distance_context_uses_training_only_leave_one_out_reference(self) -> None:
        training = [run(str(index))["discovery"][0] for index in range(4)]
        target = run("target")["late"][:1]
        for index, row in enumerate(training):
            for key in ("lower_afterstate_tensor", "higher_afterstate_tensor"):
                row[key]["packed_item_values"][0][0] += float(index)
        target[0]["higher_afterstate_tensor"]["packed_item_values"][0][0] += 20.0

        context = _distance_context(training, target, "packed")

        self.assertEqual(len(context["training_leave_one_out"]), 4)
        self.assertEqual(len(context["target_nearest"]), 1)
        self.assertGreater(
            context["target_nearest"][0],
            np.quantile(context["training_leave_one_out"], 0.95),
        )

    def test_diagnosis_keeps_target_out_of_training(self) -> None:
        training = [run("1"), run("2")]
        target = run("3")
        evaluation = evaluate_frozen({
            "status": "frozen_awaiting_new_physical_run",
            "confirmation_gate": {
                "minimum_coverage": 0.0, "maximum_errors": 10,
            },
        }, training, target)

        report = diagnose(training, target, evaluation)

        self.assertFalse(report["evaluation_rows_are_training_data"])
        self.assertEqual(report["training_run_ids"], ["1", "2"])
        self.assertEqual(report["target_run_id"], "3")
        self.assertEqual(
            report["directional_rows"],
            len(_eligible(target["late"], "fill_score_proxy")),
        )
        self.assertEqual(
            report["posthoc_training_support_gate"]["status"],
            "diagnostic_only_not_preregistered",
        )

    def test_rejects_evaluation_for_a_different_target(self) -> None:
        training = [run("1"), run("2")]
        target = run("3")
        with self.assertRaisesRegex(ValueError, "do not match"):
            diagnose(training, target, {"target_run_id": "4", "rows": []})


if __name__ == "__main__":
    unittest.main()
