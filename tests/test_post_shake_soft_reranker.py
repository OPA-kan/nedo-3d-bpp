from __future__ import annotations

import unittest
import copy

from scripts.develop_post_shake_soft_reranker import (
    soft_topology_delta,
    soft_topology_summary,
)
from scripts.evaluate_prospective_phase_soft_policy import evaluate
from scripts.train_phase_conditioned_soft_policy import (
    phase_conditioned_soft_features,
    phase_conditioned_pooled_features,
    phase_observables,
    teacher_signature,
)


def state(items: list[list[float]]) -> dict:
    return {
        "container_features": ["length", "width", "height"],
        "container_values": [[2.0, 1.0, 1.5]],
        "packed_item_features": [
            "container_index", "local_x", "local_y", "local_z",
            "length", "width", "height", "mass", "is_prioritized", "is_soft",
        ],
        "packed_item_values": items,
        "visible_item_features": [],
        "visible_item_values": [],
    }


class PostShakeSoftRerankerTests(unittest.TestCase):
    def test_direct_ordinary_cover_is_counted(self) -> None:
        lower_soft = [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]
        upper_plain = [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 0]

        values = soft_topology_summary(state([lower_soft, upper_plain]))

        self.assertEqual(values[3:7], [1.0, 1.0, 1.0, 1.0])

    def test_soft_on_soft_is_not_a_soft_violation(self) -> None:
        lower_soft = [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]
        upper_soft = [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 1]

        values = soft_topology_summary(state([lower_soft, upper_soft]))

        self.assertEqual(values[3:7], [0.0, 0.0, 0.0, 0.0])

    def test_priority_is_independent_of_soft_on_all_upper_classes(self) -> None:
        lower_soft = [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]
        for upper_priority, upper_soft, expected in (
            (0, 0, 1.0), (1, 0, 1.0), (0, 1, 0.0), (1, 1, 0.0),
        ):
            with self.subTest(priority=upper_priority, soft=upper_soft):
                upper = [
                    0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3,
                    upper_priority, upper_soft,
                ]
                values = soft_topology_summary(state([lower_soft, upper]))
                self.assertEqual(values[3], expected)

    def test_soft_topology_delta_negates_when_afterstates_swap(self) -> None:
        clean = state([[0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]])
        covered = state([
            [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1],
            [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 0],
        ])
        row = {
            "lower_afterstate_tensor": clean,
            "higher_afterstate_tensor": covered,
        }

        forward = soft_topology_delta(row)
        reverse = soft_topology_delta(row, (covered, clean))

        self.assertEqual(reverse, [-value for value in forward])

    def test_phase_observables_use_state_progress_not_root_step(self) -> None:
        source = state([[0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]])
        source["visible_item_features"] = [
            "length", "width", "height", "is_prioritized", "is_soft",
        ]
        source["visible_item_values"] = [
            [0.3, 0.3, 0.2, 0, 0],
            [0.3, 0.3, 0.2, 0, 1],
            [0.3, 0.3, 0.2, 1, 0],
        ]

        phase = phase_observables(source)

        self.assertEqual(phase[0], 1.0)
        self.assertEqual(phase[1], 0.25)
        self.assertEqual(phase[2], 0.0625)
        self.assertAlmostEqual(phase[6], 1 / 3)

    def test_phase_conditioned_features_remain_pair_antisymmetric(self) -> None:
        clean = state([[0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]])
        covered = state([
            [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1],
            [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 0],
        ])
        row = {
            "source_state_tensor": clean,
            "lower_afterstate_tensor": clean,
            "higher_afterstate_tensor": covered,
        }
        reverse = dict(
            row,
            lower_afterstate_tensor=covered,
            higher_afterstate_tensor=clean,
        )

        forward_values = phase_conditioned_soft_features(row)
        reverse_values = phase_conditioned_soft_features(reverse)

        self.assertEqual(reverse_values, [-value for value in forward_values])
        pooled_forward = phase_conditioned_pooled_features(row)
        pooled_reverse = phase_conditioned_pooled_features(reverse)
        self.assertEqual(
            pooled_reverse, [-value for value in pooled_forward]
        )

    def test_teacher_signature_excludes_labels(self) -> None:
        example = {
            "case_id": "case", "root_step": 12,
            "source_state_tensor": state([]),
            "lower_action_tensor": {"values": [1]},
            "higher_action_tensor": {"values": [2]},
            "distributional_continuation_labels": {"x": {"relation": "a"}},
        }
        relabeled = copy.deepcopy(example)
        relabeled["distributional_continuation_labels"]["x"]["relation"] = "b"

        self.assertEqual(teacher_signature(example), teacher_signature(relabeled))

    def test_prospective_policy_rejects_its_training_run(self) -> None:
        policy = {
            "status": "prospective_evaluation_only",
            "target": "post_shake_soft_covered_by_other",
            "label_family": "distributional_continuation_labels",
            "source_run_id": "same",
        }

        with self.assertRaisesRegex(ValueError, "different physical run"):
            evaluate(policy, {"source_run_id": "same"}, [])


if __name__ == "__main__":
    unittest.main()
