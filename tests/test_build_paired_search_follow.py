import copy
import unittest

from scripts.build_paired_search_follow import (
    compare_arms,
    select_follow_decision,
)


def action(x):
    return {
        "item_idx": int(x * 10),
        "container_idx": 0,
        "place_pos": [x, 0.0, 0.5],
        "orientation": 0,
    }


def graph(*, horizon=3, branch_factor=3, candidate_value=5.0,
          candidate_soft_delta=0.0):
    def edge(edge_id, target, rank, command, soft_delta=0.0):
        return {
            "edge_id": edge_id,
            "source": "root",
            "target": target,
            "command_action": command,
            "selection": {"rank": rank},
            "immediate_outcomes": {
                "is_included": True,
                "is_valid": True,
                "is_placed_safe": True,
                "soft_covered_by_other_delta": soft_delta,
            },
        }

    return {
        "graph_id": f"h{horizon}-b{branch_factor}",
        "root_snapshot_id": "snapshot-1",
        "case_id": "case-1",
        "root_step": 9,
        "future_stream_id": "stream-1",
        "budget": {"horizon": horizon, "branch_factor": branch_factor},
        "nodes": [
            {
                "node_id": "root", "depth": 0,
                "board_fingerprint": "board-1", "terminal_reason": None,
                "cumulative_outcomes": {"fill_score_proxy": 0.0},
            },
            {
                "node_id": "inc", "depth": horizon,
                "board_fingerprint": "inc-board", "terminal_reason": None,
                "cumulative_outcomes": {"fill_score_proxy": 2.0},
            },
            {
                "node_id": "candidate", "depth": horizon,
                "board_fingerprint": "candidate-board", "terminal_reason": None,
                "cumulative_outcomes": {
                    "fill_score_proxy": candidate_value,
                },
            },
        ],
        "edges": [
            edge("inc-edge", "inc", 0, action(0.1)),
            edge(
                "candidate-edge", "candidate", 1, action(0.2),
                candidate_soft_delta,
            ),
        ],
    }


class PairedSearchFollowGateTests(unittest.TestCase):
    def test_gate_requires_same_hard_safe_improvement_across_horizon_and_width(self):
        decision = select_follow_decision(
            [graph(horizon=3, branch_factor=3),
             graph(horizon=4, branch_factor=3),
             graph(horizon=3, branch_factor=2)],
            min_advantage=1.0,
            required_horizons={3, 4},
            required_branch_factors={2, 3},
        )

        self.assertEqual(decision["status"], "follow")
        self.assertEqual(decision["search_action"], action(0.2))
        self.assertEqual(decision["incumbent_action"], action(0.1))
        self.assertEqual(len(decision["views"]), 3)

    def test_gate_holds_when_a_search_view_disagrees(self):
        disagreeing = graph(horizon=4, branch_factor=3, candidate_value=1.0)
        decision = select_follow_decision(
            [graph(), disagreeing, graph(horizon=3, branch_factor=2)],
            min_advantage=0.5,
            required_horizons={3, 4},
            required_branch_factors={2, 3},
        )

        self.assertEqual(decision["status"], "hold")
        self.assertIn("view_disagreement", decision["reasons"])

    def test_gate_holds_when_the_candidate_breaks_soft_nonregression(self):
        unsafe = graph(candidate_soft_delta=1.0)
        decision = select_follow_decision(
            [unsafe, graph(horizon=4), graph(branch_factor=2)],
            min_advantage=0.5,
            required_horizons={3, 4},
            required_branch_factors={2, 3},
        )

        self.assertEqual(decision["status"], "hold")
        self.assertIn("view_disagreement", decision["reasons"])

    def test_explicit_live_incumbent_overrides_fixed_budget_rank_zero(self):
        graphs = [
            graph(horizon=3, branch_factor=3),
            graph(horizon=4, branch_factor=3),
            graph(horizon=3, branch_factor=2),
        ]
        for view in graphs:
            view["edges"][0]["selection"]["rank"] = 1
            view["edges"][1]["selection"]["rank"] = 0

        without_live_action = select_follow_decision(
            graphs, min_advantage=1.0,
            required_horizons={3, 4}, required_branch_factors={2, 3},
        )
        with_live_action = select_follow_decision(
            graphs, min_advantage=1.0,
            required_horizons={3, 4}, required_branch_factors={2, 3},
            incumbent_action=action(0.1),
        )

        self.assertEqual(without_live_action["status"], "hold")
        self.assertEqual(with_live_action["status"], "follow")
        self.assertEqual(with_live_action["incumbent_action"], action(0.1))

    def test_pair_comparison_keeps_axes_separate(self):
        baseline = {
            "steps": 20,
            "terminated": True,
            "truncated": False,
            "evaluation": {
                "fill_score": 50.0,
                "num_placed_items": 20,
                "step_metrics": [{
                    "center_of_mass_z": 1.0,
                    "soft_covered_by_other": 1,
                    "priority_covered_by_other": 0,
                    "priority_misrouted": 0,
                }],
                "shake_response": {"shake_peak_kinetic_energy": 2.0},
            },
            "captures": [{"model_visible_state_signature": "base-state"}],
        }
        search = copy.deepcopy(baseline)
        search["evaluation"]["fill_score"] = 55.0
        search["evaluation"]["step_metrics"][0]["center_of_mass_z"] = 1.2
        search["captures"] = [{"model_visible_state_signature": "search-state"}]

        result = compare_arms(baseline, search)

        self.assertEqual(result["raw_deltas"]["fill"], 5.0)
        self.assertAlmostEqual(result["raw_deltas"]["cog"], 0.2)
        self.assertEqual(result["pareto_relation"], "incomparable")
        self.assertEqual(result["new_downstream_state_count"], 1)


if __name__ == "__main__":
    unittest.main()
