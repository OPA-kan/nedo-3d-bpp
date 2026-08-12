from __future__ import annotations

import unittest

from scripts.summarize_counterfactual_graph_signal import (
    render_markdown,
    summarize_graph_signal,
    summarize_paths,
)


def graph_fixture():
    return {
        "graph_id": "g1",
        "case_id": "case",
        "root_step": 12,
        "budget": {"horizon": 1},
        "provenance": {"scenario_axes": {"container_count": 2}},
        "nodes": [
            {"node_id": "root", "depth": 0, "state_tensor": {
                "visible_item_features": ["mass"],
                "visible_item_indices": [1, 2],
                "visible_item_values": [[1.5], [2.5]],
            }, "cumulative_outcomes": {
                "placed_count": 12, "fill_score_proxy": 10.0,
                "com_z": 0.6, "surface_total_variation": 0.02,
                "priority_misrouted": 0, "soft_covered_by_other": 0,
            }, "terminal_reason": None},
            {"node_id": "low", "depth": 1, "cumulative_outcomes": {
                "placed_count": 13, "fill_score_proxy": 12.0,
                "com_z": 0.55, "surface_total_variation": 0.019,
                "priority_misrouted": 0, "soft_covered_by_other": 0,
            }, "terminal_reason": None},
            {"node_id": "high", "depth": 1, "cumulative_outcomes": {
                "placed_count": 13, "fill_score_proxy": 11.0,
                "com_z": 0.58, "surface_total_variation": 0.021,
                "priority_misrouted": 0, "soft_covered_by_other": 1,
            }, "terminal_reason": "physical_failure"},
        ],
        "edges": [
            {"source": "root", "target": "low", "command_action": {
                "item_idx": 0, "container_idx": 0,
                "place_pos": [0.1, 0.2, 0.3], "orientation": 0,
            }, "selection": {
                "score": 1.0, "stable_item_index": 1,
                "candidate_kind": "settled_candidate",
            }, "immediate_outcomes": {"is_placed_safe": True}},
            {"source": "root", "target": "high", "command_action": {
                "item_idx": 1, "container_idx": 0,
                "place_pos": [0.4, 0.5, 0.6], "orientation": 2,
            }, "selection": {
                "score": 2.0, "stable_item_index": 2,
                "candidate_kind": "release_candidate",
            }, "immediate_outcomes": {"is_placed_safe": False}},
        ],
    }


class CounterfactualGraphSignalTests(unittest.TestCase):
    def test_finds_lower_score_reachable_leaf_and_failure_label(self):
        summary = summarize_graph_signal(graph_fixture(), source="graph.json")

        self.assertEqual(summary["terminal_trajectory_count"], 2)
        self.assertEqual(summary["terminal_reasons"], {
            "horizon": 1, "physical_failure": 1,
        })
        self.assertEqual(summary["physically_failed_edges"], 1)
        self.assertEqual(
            summary["lower_score_better_reachable_leaf_counts"][
                "fill_score_proxy"
            ],
            1,
        )
        self.assertEqual(
            summary["unequal_score_pairs_with_different_downstream_ranges"],
            1,
        )
        pair = summary["sibling_pairs"][0]
        self.assertEqual(
            pair["lower_action_tensor"]["contract"],
            "observed_candidate_action_no_future_labels",
        )
        self.assertEqual(pair["lower_action_tensor"]["values"][-1], 1.5)
        self.assertEqual(pair["higher_action_tensor"]["values"][5], 1.0)

    def test_equal_score_separation_is_counted_without_a_threshold(self):
        graph = graph_fixture()
        graph["edges"][1]["selection"]["score"] = 1.0

        summary = summarize_graph_signal(graph, source="graph.json")

        self.assertEqual(summary["equal_immediate_score_pairs"], 1)
        self.assertEqual(
            summary["equal_score_pairs_with_different_downstream_ranges"], 1
        )
        self.assertFalse(
            any(summary["lower_score_better_reachable_leaf_counts"].values())
        )

    def test_matrix_summary_does_not_claim_training_readiness(self):
        class Path:
            def read_text(self, encoding):
                return __import__("json").dumps(graph_fixture())

            def as_posix(self):
                return "graph.json"

        summary = summarize_paths([Path()], run_id="123")

        self.assertEqual(
            summary["training_readiness"],
            "not_established_preregistered_gates_failed",
        )
        self.assertEqual(summary["run_id"], "123")
        self.assertFalse(summary["readiness_gates"]["minimum_16_graphs"])
        self.assertEqual(
            summary["root_step_partitions"]["discovery_step_lt_15"][
                "graph_count"
            ],
            1,
        )
        self.assertIn("not_established", render_markdown(summary))


if __name__ == "__main__":
    unittest.main()
