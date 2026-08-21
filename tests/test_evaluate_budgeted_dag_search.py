import unittest

from scripts.evaluate_budgeted_dag_search import (
    constrained_root_oracle,
    evaluate_graph,
    puct_search,
    root_scan,
)


def search_graph(*, soft_violation=False):
    nodes = [
        {
            "node_id": "root", "depth": 0, "terminal_reason": None,
            "cumulative_outcomes": {"fill_score_proxy": 0.0},
        },
        {
            "node_id": "a1", "depth": 1, "terminal_reason": None,
            "cumulative_outcomes": {"fill_score_proxy": 1.0},
        },
        {
            "node_id": "a2", "depth": 2, "terminal_reason": None,
            "cumulative_outcomes": {"fill_score_proxy": 2.0},
        },
        {
            "node_id": "b1", "depth": 1, "terminal_reason": None,
            "cumulative_outcomes": {"fill_score_proxy": 1.5},
        },
        {
            "node_id": "b2", "depth": 2, "terminal_reason": None,
            "cumulative_outcomes": {"fill_score_proxy": 5.0},
        },
    ]

    def edge(edge_id, source, target, rank, **outcome):
        return {
            "edge_id": edge_id,
            "source": source,
            "target": target,
            "selection": {"rank": rank, "score": float(-rank)},
            "immediate_outcomes": {
                "is_included": True,
                "is_valid": True,
                "is_placed_safe": True,
                "priority_misrouted_delta": 0.0,
                "priority_covered_by_other_delta": 0.0,
                "soft_covered_by_other_delta": 0.0,
                "post_shake_priority_misrouted_delta": 0.0,
                "post_shake_priority_covered_by_other_delta": 0.0,
                "post_shake_soft_covered_by_other_delta": 0.0,
                "post_shake_soft_clean_to_covered_events_delta": 0.0,
                **outcome,
            },
        }

    return {
        "graph_id": "search-fixture",
        "case_id": "fixture",
        "root_step": 10,
        "budget": {"horizon": 2, "branch_factor": 2},
        "nodes": nodes,
        "edges": [
            edge("root-a", "root", "a1", 0),
            edge(
                "root-b", "root", "b1", 1,
                soft_covered_by_other_delta=1.0 if soft_violation else 0.0,
            ),
            edge("a-leaf", "a1", "a2", 0),
            edge("b-leaf", "b1", "b2", 0),
        ],
    }


class BudgetedDagSearchTests(unittest.TestCase):
    def test_full_oracle_finds_the_best_reachable_root(self):
        oracle = constrained_root_oracle(search_graph())

        self.assertEqual(oracle["optimal_edge_ids"], ["root-b"])
        self.assertEqual(oracle["root_values"]["root-a"], 2.0)
        self.assertEqual(oracle["root_values"]["root-b"], 5.0)

    def test_hard_attribute_constraint_removes_a_soft_regression(self):
        graph = search_graph(soft_violation=True)

        hard = constrained_root_oracle(graph, hard_attributes=True)
        physical_only = constrained_root_oracle(
            graph, hard_attributes=False
        )

        self.assertEqual(hard["optimal_edge_ids"], ["root-a"])
        self.assertIsNone(hard["root_values"]["root-b"])
        self.assertEqual(physical_only["optimal_edge_ids"], ["root-b"])

    def test_perfect_leaf_value_makes_puct_recover_the_better_root(self):
        result = puct_search(
            search_graph(), simulations=40, prior="rank",
            leaf_value="oracle", cpuct=2.0,
        )

        self.assertEqual(result["chosen_edge_id"], "root-b")
        self.assertEqual(sum(result["root_visits"].values()), 40)
        self.assertAlmostEqual(sum(result["policy"].values()), 1.0)
        self.assertLessEqual(result["revealed_edge_count"], 4)

    def test_q_selection_uses_the_value_correction_before_visits_converge(self):
        result = puct_search(
            search_graph(), simulations=12, prior="rank",
            leaf_value="oracle", cpuct=2.0,
        )

        self.assertEqual(result["chosen_edge_id"], "root-a")
        self.assertEqual(result["chosen_by_q_edge_id"], "root-b")
        self.assertGreater(result["root_q"]["root-b"], result["root_q"]["root-a"])

    def test_full_root_scan_exposes_the_immediate_fill_baseline(self):
        partial = root_scan(search_graph(), probes=1)
        complete = root_scan(search_graph(), probes=2)

        self.assertEqual(partial["chosen_edge_id"], "root-a")
        self.assertEqual(complete["chosen_edge_id"], "root-b")
        self.assertEqual(complete["revealed_edge_count"], 2)

    def test_evaluation_reports_incumbent_and_search_against_same_oracle(self):
        result = evaluate_graph(
            search_graph(), simulation_budgets=[2, 40], cpuct_values=[2.0]
        )

        self.assertEqual(result["incumbent_edge_id"], "root-a")
        self.assertFalse(result["incumbent_optimal"])
        self.assertTrue(result["full_root_scan_optimal"])
        self.assertFalse(result["future_sensitive"])
        perfect = next(
            row for row in result["searches"]
            if row["algorithm"] == "puct-rank-oracle-v"
            and row["simulations"] == 40
        )
        self.assertTrue(perfect["oracle_optimal"])
        self.assertEqual(perfect["oracle_regret"], 0.0)


if __name__ == "__main__":
    unittest.main()
