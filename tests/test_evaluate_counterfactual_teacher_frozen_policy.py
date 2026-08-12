from __future__ import annotations

import unittest

from scripts.evaluate_counterfactual_teacher_discovery import frozen_axis_policy
from scripts.evaluate_counterfactual_teacher_frozen_policy import (
    evaluate_frozen_policy,
)
from tests.test_evaluate_counterfactual_teacher_discovery import row


class FrozenCounterfactualPolicyTests(unittest.TestCase):
    def test_evaluates_only_the_fixed_axis_policy(self):
        discovery = [
            row("a", "g1", -0.3, "lower_immediate_score_better"),
            row("b", "g2", 0.3, "higher_immediate_score_better"),
        ]
        for example in discovery:
            example["labels"]["com_z"] = example["labels"]["fill_score_proxy"]
            example["labels"]["surface_total_variation"] = example["labels"]["fill_score_proxy"]
        late = [row("h", "g3", 0.2, "higher_immediate_score_better")]
        late[0]["labels"]["com_z"] = late[0]["labels"]["fill_score_proxy"]
        late[0]["labels"]["surface_total_variation"] = late[0]["labels"]["fill_score_proxy"]
        policy = frozen_axis_policy({"axes": {
            metric: {
                "directional_rows": 2,
                "models": {
                    "action_only_ridge": {"correct": 1, "total": 2},
                    "candidate_local_state_ridge": {"correct": 1, "total": 2},
                },
                "permuted_local_ridge_correct": {
                    "values": [1], "minimum": 1, "median": 1, "maximum": 1,
                },
            }
            for metric in ("fill_score_proxy", "com_z", "surface_total_variation")
        }})

        report = evaluate_frozen_policy(policy, discovery, late)

        self.assertEqual(
            report["axes"]["fill_score_proxy"]["selected_model"],
            "action_only_ridge",
        )
        self.assertIn("passed", report["candidate_local_gate"])

    def test_rejects_a_policy_changed_after_selection(self):
        policy = {
            "axes": {}, "late_holdout_accessed_for_selection": False,
        }
        with self.assertRaisesRegex(ValueError, "preregistered"):
            evaluate_frozen_policy(policy, [], [])


if __name__ == "__main__":
    unittest.main()
