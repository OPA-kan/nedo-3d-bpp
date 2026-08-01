from __future__ import annotations

import copy
import time
import unittest
from unittest import mock

import numpy as np

from agent import agent


def item(index):
    return {
        "index": index,
        "length": 0.2,
        "width": 0.2,
        "height": 0.2,
        "mass": 1.0,
    }


def container():
    return {
        "length": 2.0,
        "width": 2.0,
        "height": 2.0,
        "thickness": 0.02,
        "buffer": 0.0,
        "cut_x": 0.0,
        "cut_y": 0.0,
        "center_x": 0.0,
        "packed_items": [],
    }


def decision(score, item_idx, orientation=0, x=0.0):
    candidate = agent.AABB(
        center=(x, 0.0, 0.12),
        size=(0.2, 0.2, 0.2),
        name="settled_candidate",
    )
    return agent.PlacementDecision(
        action={
            "item_idx": item_idx,
            "container_idx": 0,
            "place_pos": np.asarray(candidate.center, dtype=np.float32),
            "orientation": orientation,
        },
        candidate=candidate,
        score=score,
    )


class ItemDiverseSearchTests(unittest.TestCase):
    def test_global_score_cannot_fill_the_item_diverse_beam(self):
        pool = [item(0), item(1)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        candidates = [
            (0, pool[0], 0, 0, decision(10.0, 0, x=0.0).candidate),
            (0, pool[0], 0, 1, decision(9.0, 0, 1, x=0.1).candidate),
            (0, pool[0], 0, 2, decision(8.0, 0, 2, x=0.2).candidate),
            (1, pool[1], 0, 0, decision(7.0, 1, x=0.3).candidate),
        ]
        score_by_x = {0.0: 10.0, 0.1: 9.0, 0.2: 8.0, 0.3: 7.0}

        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter(candidates),
            ),
            mock.patch.object(
                agent.Ranker,
                "score",
                side_effect=lambda candidate, *_args: score_by_x[
                    round(float(candidate.center[0]), 1)
                ],
            ),
        ):
            shortlist, _probes = agent.PlacementCore.item_diverse_candidates(
                observation,
                list(enumerate(pool)),
                item_k=2,
                validation_budget=16,
            )

        self.assertEqual(
            [entry.action["item_idx"] for entry in shortlist],
            [0, 1],
        )
        self.assertEqual([entry.score for entry in shortlist], [10.0, 7.0])


class FutureOptionValueTests(unittest.TestCase):
    def test_nearby_floor_candidates_share_one_support_region(self):
        target = container()
        first = decision(1.0, 0, x=-0.3).candidate
        second = decision(1.0, 1, x=0.3).candidate

        self.assertEqual(
            agent.candidate_support_region_signature(first, target),
            agent.candidate_support_region_signature(second, target),
        )

    def test_fixed_probe_budget_counts_distinct_option_dimensions(self):
        pool = [item(index) for index in range(4)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        placed = decision(10.0, 0)
        probes = [
            decision(1.0, 1, orientation=0, x=0.1),
            decision(1.0, 1, orientation=1, x=0.2),
            decision(1.0, 2, orientation=0, x=0.3),
            decision(1.0, 3, orientation=0, x=0.4),
        ]
        signatures = iter(("region-a", "region-a", "region-b"))

        with (
            mock.patch.object(agent, "apply_placement_decision"),
            mock.patch.object(agent.Geometry, "valid", return_value=True),
            mock.patch.object(
                agent,
                "candidate_support_region_signature",
                side_effect=lambda *_args: next(signatures),
            ),
        ):
            value = agent.evaluate_future_option_value(
                observation,
                pool,
                placed,
                probes,
                validation_budget=3,
            )

        self.assertEqual(value.evaluated_candidates, 3)
        self.assertEqual(value.feasible_items, 2)
        self.assertEqual(value.feasible_item_orientations, 3)
        self.assertEqual(value.distinct_support_regions, 2)
        self.assertEqual(value.valid_candidates, 3)

    def test_placed_item_is_not_leaked_into_the_future_pool(self):
        pool = [item(0), item(1)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        probes = [decision(2.0, 0), decision(1.0, 1)]

        with (
            mock.patch.object(agent, "apply_placement_decision"),
            mock.patch.object(agent.Geometry, "valid", return_value=True),
            mock.patch.object(
                agent,
                "candidate_support_region_signature",
                return_value="floor",
            ),
        ):
            value = agent.evaluate_future_option_value(
                observation,
                pool,
                decision(3.0, 0),
                probes,
                validation_budget=2,
            )

        self.assertEqual(value.evaluated_candidates, 1)
        self.assertEqual(value.feasible_items, 1)

    def test_lexicographic_value_breaks_only_the_q_live_cohort(self):
        best_q = decision(10.0, 0)
        resilient = decision(9.90, 1)
        outside_band = decision(9.70, 2)
        low = agent.FutureOptionValue(1, 1, 1, 10, 10)
        high = agent.FutureOptionValue(3, 4, 2, 20, 20)

        selected = agent.select_future_option_evaluation(
            [
                agent.FutureOptionEvaluation(best_q, low),
                agent.FutureOptionEvaluation(resilient, high),
                agent.FutureOptionEvaluation(outside_band, high),
            ],
            q_band=0.15,
        )

        self.assertIs(selected.decision, resilient)


class FeatureFlagTests(unittest.TestCase):
    def test_enabled_path_selects_residual_value_inside_q_band(self):
        pool = [item(0), item(1)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        q_best = decision(10.0, 0)
        resilient = decision(9.9, 1)
        low = agent.FutureOptionValue(1, 1, 1, 4, 8)
        high = agent.FutureOptionValue(2, 3, 2, 6, 8)
        diagnostics = {"search": {"incumbent_updates": 0}}
        solver = agent.Agent("")

        with (
            mock.patch.object(
                agent.PlacementCore,
                "item_diverse_candidates",
                return_value=([q_best, resilient], [q_best, resilient]),
            ),
            mock.patch.object(
                agent,
                "evaluate_future_option_value",
                side_effect=[low, high],
            ),
            mock.patch.object(agent, "FUTURE_OPTION_Q_BAND", 0.15),
        ):
            selected = solver._future_option_choice(
                observation,
                pool,
                list(enumerate(pool)),
                deadline=time.perf_counter() + 5.0,
                diagnostics=diagnostics,
            )

        self.assertIs(selected, resilient)
        record = diagnostics["future_option_tiebreak"]
        self.assertTrue(record["changed_from_q_best"])
        self.assertFalse(record["aborted_for_deadline"])
        self.assertEqual(record["cohort_count"], 2)

    def test_off_path_does_not_call_future_option_choice(self):
        observation = {
            "pool_list": [item(0)],
            "container_list": [container()],
        }
        baseline = decision(1.0, 0)
        solver = agent.Agent("")
        solver.get_init_states(
            {
                "optimize": False,
                "lookahead_k": 1,
                "container_list": copy.deepcopy(observation["container_list"]),
            }
        )

        with (
            mock.patch.object(agent, "FUTURE_OPTION_TIEBREAK_ENABLED", False),
            mock.patch.object(
                solver,
                "_closed_loop_choice",
                return_value=baseline,
            ) as old_choice,
            mock.patch.object(
                solver,
                "_future_option_choice",
                side_effect=AssertionError("future option path must be bypassed"),
                create=True,
            ),
        ):
            action = solver.policy(observation)

        old_choice.assert_called_once()
        self.assertEqual(action["item_idx"], 0)


if __name__ == "__main__":
    unittest.main()
