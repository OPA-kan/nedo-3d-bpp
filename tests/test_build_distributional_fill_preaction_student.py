from __future__ import annotations

import unittest

from scripts.build_distributional_fill_preaction_student import (
    _action_delta,
    build_student,
    student_predictions,
)
from scripts.build_distributional_fill_shadow_model import build_model
from tests.test_evaluate_counterfactual_afterstate_value import run


class DistributionalFillPreactionStudentTests(unittest.TestCase):
    def test_action_delta_excludes_immediate_score(self) -> None:
        row = run("input-contract")["late"][0]
        names = row["lower_action_tensor"]["feature_names"]

        self.assertEqual(len(_action_delta(row)), len(names) - 1)
        self.assertIn("immediate_score", names)

    def test_student_predicts_without_target_afterstate_or_labels(self) -> None:
        training = [run("one"), run("two")]
        for physical_run in training:
            for row in physical_run["discovery"]:
                row["source_node_id"] = "source-" + row["teacher_id"]
                row["source_state_tensor"] = row["lower_afterstate_tensor"]
                row["lower_stable_item_index"] = 1
                row["higher_stable_item_index"] = 2
        shadow = build_model(training)
        student = build_student(training, shadow)
        target = run("target")["late"]
        target[0]["source_state_tensor"] = target[0]["lower_afterstate_tensor"]
        target[0]["lower_stable_item_index"] = 1
        target[0]["higher_stable_item_index"] = 2
        target[0]["source_node_id"] = "target-source"
        target[0].pop("distributional_continuation_labels")
        target[0].pop("continuation_labels")
        target[0].pop("lower_afterstate_tensor")
        target[0].pop("higher_afterstate_tensor")

        predictions = student_predictions(student, shadow, target)

        self.assertEqual(len(predictions), 1)
        self.assertIn(
            predictions[0]["student_relation"],
            ("lower_afterstate_better", "higher_afterstate_better"),
        )


if __name__ == "__main__":
    unittest.main()
