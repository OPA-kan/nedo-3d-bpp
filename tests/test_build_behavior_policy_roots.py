from __future__ import annotations

import random
import unittest
from types import SimpleNamespace

from scripts.build_behavior_policy_roots import (
    behavior_frontier,
    choose_behavior_action,
)
from scripts.build_counterfactual_graph import transition_outcomes


def action(x: float) -> dict:
    return {"item_idx": 0, "container_idx": 0, "place_pos": [x, 0, 0.5], "orientation": 0}


class BehaviorPolicyRootTests(unittest.TestCase):
    def test_transition_contract_separates_edge_outcomes_from_cumulative_state(self):
        class Evaluator:
            def settled_snapshot(self, _containers):
                return {}

        env = SimpleNamespace(
            evaluator=Evaluator(),
            container_manager=SimpleNamespace(containers=[]),
            evaluate=lambda: {
                "score_proxies": {"fill_score_proxy": 1.0},
                "items_placed": 1,
            },
            step_metrics=[],
        )
        immediate, cumulative = transition_outcomes(
            env,
            {"is_included": True, "is_valid": True, "is_placed_safe": True},
            {},
        )
        self.assertIsInstance(immediate, dict)
        self.assertIsInstance(cumulative, dict)
        self.assertIn("is_included", immediate)

    def test_frontier_keeps_live_action_first_and_only_settled_unique_alternatives(self):
        decisions = [
            SimpleNamespace(action=action(0.2), score=8.0, candidate=SimpleNamespace(name=None)),
            SimpleNamespace(action=action(0.2), score=7.0, candidate=SimpleNamespace(name=None)),
            SimpleNamespace(action=action(0.3), score=9.0, candidate=SimpleNamespace(name="release_candidate")),
            SimpleNamespace(action=action(0.4), score=6.0, candidate=SimpleNamespace(name=None)),
        ]
        frontier = behavior_frontier(action(0.1), decisions, top_k=3)
        self.assertEqual([row["action"]["place_pos"][0] for row in frontier], [0.1, 0.2, 0.4])
        self.assertEqual(frontier[0]["source"], "live_rank0")

    def test_force_rank_changes_once_and_falls_back_if_rank_is_missing(self):
        frontier = [{"action": action(x)} for x in (0.1, 0.2, 0.3)]
        rng = random.Random(1)
        chosen, rank = choose_behavior_action(
            frontier, mode="force-rank2", step=6, divergence_step=6,
            temperature=1.0, rng=rng,
        )
        self.assertEqual(rank, 2)
        self.assertEqual(chosen["place_pos"][0], 0.3)
        _chosen, rank = choose_behavior_action(
            frontier[:2], mode="force-rank2", step=6, divergence_step=6,
            temperature=1.0, rng=rng,
        )
        self.assertEqual(rank, 0)

    def test_temperature_selection_is_seed_reproducible(self):
        frontier = [{"action": action(x)} for x in (0.1, 0.2, 0.3)]
        ranks = []
        for _ in range(2):
            _chosen, rank = choose_behavior_action(
                frontier, mode="safe-temperature", step=4,
                divergence_step=6, temperature=2.0, rng=random.Random(99),
            )
            ranks.append(rank)
        self.assertEqual(ranks[0], ranks[1])

    def test_frontier_excludes_an_alternative_rejected_by_hard_constraints(self):
        decisions = [
            SimpleNamespace(action=action(0.2), score=8.0, candidate=SimpleNamespace(name=None)),
            SimpleNamespace(action=action(0.3), score=7.0, candidate=SimpleNamespace(name=None)),
        ]
        frontier = behavior_frontier(
            action(0.1), decisions, top_k=3,
            is_safe=lambda candidate: candidate["place_pos"][0] != 0.2,
        )
        self.assertEqual(
            [row["action"]["place_pos"][0] for row in frontier], [0.1, 0.3]
        )


if __name__ == "__main__":
    unittest.main()
