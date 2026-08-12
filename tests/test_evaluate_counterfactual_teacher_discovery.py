from __future__ import annotations

import unittest

from scripts.evaluate_counterfactual_teacher_discovery import (
    evaluate_discovery,
    frozen_axis_policy,
    local_pair_vector,
)


def action(x: float, score: float):
    names = [
        "container_index", "command_x", "command_y", "command_z",
        "orientation", "is_release_candidate", "immediate_score",
        "length", "width", "height", "mass", "is_prioritized", "is_soft",
    ]
    return {
        "feature_names": names,
        "values": [0, x, 0, 0.5, 0, 0, score, 0.2, 0.2, 0.2, 1, 0, 0],
    }


def state(packed_x: float):
    return {
        "container_features": [
            "length", "width", "height", "has_shelf", "is_priority_dedicated",
        ],
        "container_values": [[2.0, 1.0, 1.0, 0.0, 0.0]],
        "packed_item_features": [
            "container_index", "local_x", "local_y", "local_z",
            "length", "width", "height", "is_prioritized", "is_soft",
        ],
        "packed_item_values": [[0, packed_x, 0, 0.3, 0.2, 0.2, 0.2, 0, 0]],
        "visible_item_features": [
            "length", "width", "height", "mass", "is_prioritized", "is_soft",
        ],
        "visible_item_values": [[0.2, 0.2, 0.2, 1.0, 0, 0]],
    }


def row(name: str, graph: str, packed_x: float, relation: str):
    labels = {
        "fill_score_proxy": {"relation": relation},
        "priority_misrouted": {"relation": "equal"},
    }
    return {
        "teacher_id": name, "graph_id": graph,
        "source_state_tensor": state(packed_x),
        "lower_action_tensor": action(-0.3, 1.0),
        "higher_action_tensor": action(0.3, 2.0),
        "labels": labels,
    }


class CounterfactualTeacherDiscoveryTests(unittest.TestCase):
    def test_local_vector_changes_when_neighbour_moves(self):
        left = row("a", "g1", -0.3, "lower_immediate_score_better")
        right = row("b", "g2", 0.3, "higher_immediate_score_better")

        self.assertNotEqual(local_pair_vector(left), local_pair_vector(right))

    def test_groups_complete_graphs_and_never_requires_holdout(self):
        rows = [
            row("a", "g1", -0.3, "lower_immediate_score_better"),
            row("b", "g1", -0.2, "lower_immediate_score_better"),
            row("c", "g2", 0.3, "higher_immediate_score_better"),
            row("d", "g2", 0.2, "higher_immediate_score_better"),
        ]

        report = evaluate_discovery(rows)

        self.assertFalse(report["late_holdout_accessed"])
        self.assertEqual(report["graph_groups"], 2)
        self.assertEqual(report["axes"]["fill_score_proxy"]["directional_rows"], 4)
        self.assertEqual(report["axes"]["priority_misrouted"]["directional_rows"], 0)
        self.assertIn(
            "candidate_local_state_ridge",
            report["axes"]["fill_score_proxy"]["models"],
        )
        policy = frozen_axis_policy(report)
        self.assertFalse(policy["late_holdout_accessed_for_selection"])
        self.assertEqual(
            policy["axes"]["fill_score_proxy"], "action_only_ridge"
        )

    def test_refuses_one_graph_that_cannot_form_a_grouped_fold(self):
        with self.assertRaisesRegex(ValueError, "at least two graphs"):
            evaluate_discovery([
                row("a", "g1", 0.0, "higher_immediate_score_better")
            ])


if __name__ == "__main__":
    unittest.main()
