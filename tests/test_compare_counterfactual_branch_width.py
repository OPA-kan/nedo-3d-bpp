from __future__ import annotations

import unittest

from scripts.compare_counterfactual_branch_width import compare_graph
from tests.test_summarize_counterfactual_graph_signal import graph_fixture


class BranchWidthComparisonTests(unittest.TestCase):
    def test_matches_preregistered_root_pair_inside_b3_graph(self) -> None:
        graph = graph_fixture()
        graph["provenance"]["scenario_axes"]["stream_variant"] = "fixture"
        root = graph["nodes"][0]["node_id"]
        edges = [edge for edge in graph["edges"] if edge["source"] == root]
        self.assertGreaterEqual(len(edges), 2)
        expected = {
            "target_id": "t",
            "metric": "fill_score_proxy",
            "lower_stable_item_index": edges[0]["selection"]["stable_item_index"],
            "higher_stable_item_index": edges[1]["selection"]["stable_item_index"],
            "b2_relation": "equal",
        }
        row = compare_graph(graph, expected)
        self.assertEqual(row["target_id"], "t")
        self.assertIn(row["b3_relation"], {
            "equal", "lower_afterstate_better", "higher_afterstate_better",
        })

    def test_accepts_generic_baseline_relation(self) -> None:
        graph = graph_fixture()
        graph["provenance"]["scenario_axes"]["stream_variant"] = "fixture"
        root = graph["nodes"][0]["node_id"]
        edges = [edge for edge in graph["edges"] if edge["source"] == root]
        expected = {
            "target_id": "h4", "metric": "fill_score_proxy",
            "lower_stable_item_index": edges[0]["selection"]["stable_item_index"],
            "higher_stable_item_index": edges[1]["selection"]["stable_item_index"],
            "baseline_relation": "equal",
        }
        row = compare_graph(graph, expected)
        self.assertEqual(row["baseline_relation"], "equal")
        self.assertEqual(row["comparison_relation"], row["b3_relation"])

    def test_rejects_pair_missing_from_b3_root(self) -> None:
        graph = graph_fixture()
        graph["provenance"]["scenario_axes"]["stream_variant"] = "fixture"
        expected = {
            "target_id": "missing", "metric": "fill_score_proxy",
            "lower_stable_item_index": 9998,
            "higher_stable_item_index": 9999,
            "b2_relation": "equal",
        }
        row = compare_graph(graph, expected)
        self.assertEqual(row["status"], "sibling_pair_absent")
        self.assertFalse(row["stable"])


if __name__ == "__main__":
    unittest.main()
