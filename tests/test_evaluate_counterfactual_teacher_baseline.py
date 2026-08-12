from __future__ import annotations

import unittest

from scripts.evaluate_counterfactual_teacher_baseline import evaluate, feature_vector


def row(name: str, state_value: float, action_value: float, relation: str):
    state = {
        "container_features": ["x"], "container_values": [[state_value]],
        "packed_item_features": ["x"], "packed_item_values": [],
        "visible_item_features": ["x"], "visible_item_values": [[state_value]],
    }
    action = {
        "feature_names": ["x"], "values": [action_value],
        "contract": "observed_candidate_action_no_future_labels",
    }
    return {
        "teacher_id": name, "source_state_tensor": state,
        "lower_action_tensor": action,
        "higher_action_tensor": {**action, "values": [action_value + 1.0]},
        "labels": {"fill_score_proxy": {"relation": relation}},
    }


class CounterfactualTeacherBaselineTests(unittest.TestCase):
    def test_evaluates_holdout_without_fitting_on_it(self):
        discovery = [
            row("a", 0.0, 0.0, "lower_immediate_score_better"),
            row("b", 10.0, 5.0, "higher_immediate_score_better"),
        ]
        holdout = [row("h", 0.1, 0.1, "lower_immediate_score_better")]

        report = evaluate({"model_training_ready": True}, discovery, holdout)

        axis = report["axes"]["fill_score_proxy"]
        self.assertEqual(axis["models"]["immediate_score"]["correct"], 0)
        self.assertEqual(axis["models"]["state_action_1nn"], {"correct": 1, "total": 1})
        self.assertGreater(len(feature_vector(holdout[0], include_state=True)), 3)

    def test_rejects_incomplete_teacher_contract(self):
        with self.assertRaisesRegex(ValueError, "not model_training_ready"):
            evaluate({"model_training_ready": False}, [], [])


if __name__ == "__main__":
    unittest.main()
