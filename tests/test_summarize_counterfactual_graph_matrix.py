from __future__ import annotations

import unittest

from scripts.summarize_counterfactual_graph_matrix import (
    render_markdown,
    summarize_graph,
)


class CounterfactualMatrixSummaryTests(unittest.TestCase):
    def test_keeps_score_axes_separate_and_counts_failures(self):
        graph = {
            "graph_id": "g1",
            "case_id": "m-dual-shelf-mixed",
            "root_step": 15,
            "budget": {"horizon": 3, "branch_factor": 2},
            "provenance": {
                "scenario_axes": {
                    "container_count": 2,
                    "shelf_count": 1,
                    "pool_width": 20,
                }
            },
            "nodes": [
                {
                    "depth": 0,
                    "terminal_reason": None,
                    "cumulative_outcomes": {
                        "placed_count": 15,
                        "fill_score_proxy": 20.0,
                        "com_z": 0.6,
                        "priority_misrouted": 0,
                        "soft_covered_by_other": 1,
                    },
                },
                {
                    "depth": 1,
                    "terminal_reason": "physical_failure",
                    "cumulative_outcomes": {
                        "placed_count": 15,
                        "fill_score_proxy": 20.0,
                        "com_z": 0.6,
                        "priority_misrouted": 0,
                        "soft_covered_by_other": 1,
                    },
                },
            ],
            "edges": [
                {
                    "selection": {"stable_item_index": 7},
                    "immediate_outcomes": {
                        "is_placed_safe": False,
                        "settle_angle_deg": 35.0,
                    },
                }
            ],
        }
        row = summarize_graph(graph, source="graph.json")
        self.assertEqual(row["physically_failed_edges"], 1)
        self.assertEqual(row["terminal_reasons"], {"physical_failure": 1})
        self.assertEqual(row["ranges"]["placed_count"]["min"], 15.0)
        self.assertEqual(row["ranges"]["com_z"]["max"], 0.6)
        self.assertEqual(row["ranges"]["settle_angle_deg"]["max"], 35.0)
        self.assertIn("CoG", render_markdown({
            "graph_count": 1,
            "condition_count": 1,
            "total_edges": 1,
            "physically_safe_edges": 0,
            "physically_failed_edges": 1,
            "graphs": [row],
        }))


if __name__ == "__main__":
    unittest.main()
