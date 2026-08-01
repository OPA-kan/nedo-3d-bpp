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
            shortlist, _probes, _route_probes = (
                agent.PlacementCore.item_diverse_candidates(
                    observation,
                    list(enumerate(pool)),
                    item_k=2,
                    validation_budget=16,
                )
            )

        self.assertEqual(
            [entry.action["item_idx"] for entry in shortlist],
            [0, 1],
        )
        self.assertEqual([entry.score for entry in shortlist], [10.0, 7.0])

    def test_route_probe_population_preserves_distinct_corridor_classes(self):
        pool = [item(0)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        candidates = [
            (0, pool[0], 0, 0, decision(10.0, 0, x=-0.8).candidate),
            (0, pool[0], 0, 0, decision(9.0, 0, x=0.8).candidate),
        ]

        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter(candidates),
            ),
            mock.patch.object(
                agent.Ranker,
                "score",
                side_effect=[10.0, 9.0],
            ),
            mock.patch.object(
                agent,
                "candidate_support_region_signature",
                return_value="floor",
            ),
            mock.patch.object(
                agent,
                "route_corridor_class_signature",
                side_effect=lambda candidate, _container: (
                    "left" if candidate.center[0] < 0.0 else "right"
                ),
            ),
            mock.patch.object(agent, "FUTURE_OPTION_PROBES_PER_SIGNATURE", 1),
            mock.patch.object(
                agent,
                "FUTURE_OPTION_ROUTE_SHADOW_ENABLED",
                True,
            ),
        ):
            _shortlist, probes, route_probes = (
                agent.PlacementCore.item_diverse_candidates(
                    observation,
                    list(enumerate(pool)),
                    item_k=1,
                    validation_budget=4,
                )
            )

        self.assertEqual(len(probes), 1)
        self.assertEqual(
            {round(float(entry.candidate.center[0]), 1) for entry in route_probes},
            {-0.8, 0.8},
        )

    def test_route_probe_instrumentation_is_zero_cost_when_flag_is_off(self):
        pool = [item(0)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        candidate = decision(10.0, 0).candidate

        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter([(0, pool[0], 0, 0, candidate)]),
            ),
            mock.patch.object(agent.Ranker, "score", return_value=10.0),
            mock.patch.object(
                agent,
                "candidate_support_region_signature",
                return_value="floor",
            ),
            mock.patch.object(
                agent,
                "route_corridor_class_signature",
            ) as corridor_signature,
            mock.patch.object(
                agent,
                "FUTURE_OPTION_ROUTE_SHADOW_ENABLED",
                False,
            ),
        ):
            _shortlist, _probes, route_probes = (
                agent.PlacementCore.item_diverse_candidates(
                    observation,
                    list(enumerate(pool)),
                    item_k=1,
                    validation_budget=4,
                )
            )

        corridor_signature.assert_not_called()
        self.assertEqual(route_probes, [])


class FutureOptionValueTests(unittest.TestCase):
    def test_route_corridor_signature_matches_existing_contract(self):
        target = container()
        target["cut_x"] = 0.25
        for width in (0.1, 0.4, 0.8):
            for x in (-1.2, -0.8, -0.2, 0.0, 0.4, 0.9, 1.2):
                candidate = agent.AABB(
                    center=(x, 0.2, 0.4),
                    size=(width, 0.2, 0.3),
                    name="release_candidate",
                )
                self.assertEqual(
                    agent.route_corridor_class_signature(candidate, target),
                    agent.future_corridor_class_signature(candidate, target),
                )

    def test_item_and_pose_classes_collapse_only_physical_equivalents(self):
        containers = [container()]
        first = item(10)
        second = item(11)
        different_mass = {**item(12), "mass": 2.0}

        self.assertEqual(
            agent.future_item_class_signature(first, containers),
            agent.future_item_class_signature(second, containers),
        )
        self.assertNotEqual(
            agent.future_item_class_signature(first, containers),
            agent.future_item_class_signature(different_mass, containers),
        )
        self.assertEqual(
            agent.future_pose_class_signature(first, 0, containers),
            agent.future_pose_class_signature(second, 1, containers),
        )

    def test_static_conflict_capacity_respects_item_identity_and_overlap(self):
        options = [
            (0, 10, 0.008, 1.0, agent.AABB((0.0, 0.0, 0.1), (0.2,) * 3)),
            # Same item, separate anchor: cannot consume the item twice.
            (0, 10, 0.008, 1.0, agent.AABB((0.8, 0.0, 0.1), (0.2,) * 3)),
            # Different item but overlaps the first option.
            (0, 11, 0.027, 1.0, agent.AABB((0.0, 0.0, 0.15), (0.3,) * 3)),
            # Different item and disjoint: can coexist with item 11.
            (0, 12, 0.001, 1.0, agent.AABB((0.8, 0.0, 0.05), (0.1,) * 3)),
        ]

        count, volume = agent.greedy_future_probe_capacity(options)

        self.assertEqual(count, 2)
        self.assertAlmostEqual(volume, 0.035)

    def test_shadow_descriptors_do_not_change_the_live_rank_key(self):
        baseline = agent.FutureOptionValue(2, 3, 1, 5, 8)
        rich_shadow = agent.FutureOptionValue(
            2,
            3,
            1,
            5,
            8,
            feasible_item_classes=9,
            feasible_pose_classes=10,
            distinct_corridor_classes=11,
            distinct_action_classes=12,
            distinct_item_class_volume_sum=13.0,
            max_feasible_item_volume=14.0,
            greedy_packable_count=15,
            greedy_packable_volume=16.0,
            route_baseline_candidates=17,
            route_survived_candidates=18,
            route_lost_candidates=19,
            space_lost_candidates=20,
            route_survival_share=0.25,
            route_item_survival_share=0.5,
            route_volume_survival_share=0.75,
        )

        self.assertEqual(baseline.rank_key(), rich_shadow.rank_key())

    def test_route_survival_separates_corridor_only_from_space_loss(self):
        pool = [item(index) for index in range(4)]
        observation = {
            "pool_list": pool,
            "container_list": [container()],
        }
        placed = decision(10.0, 0)
        probes = [
            decision(3.0, 1, orientation=0, x=0.1),
            decision(2.0, 2, orientation=1, x=0.2),
            decision(1.0, 3, orientation=0, x=0.3),
        ]

        with (
            mock.patch.object(
                agent,
                "apply_placement_decision",
                return_value=agent.PlacementTrace(
                    item_index=0,
                    container_idx=0,
                    orientation=0,
                    candidate=placed.candidate,
                    support=agent.SupportMetrics(1.0, 1.0, 1, 1.0),
                    mass=1.0,
                ),
            ),
            mock.patch.object(agent.Geometry, "valid", return_value=True),
            mock.patch.object(
                agent.Geometry,
                "structural_rejection_reason",
                side_effect=[None, None, "static_geometry"],
            ),
            mock.patch.object(
                agent,
                "placement_blocks_transport",
                side_effect=[False, True],
            ),
            mock.patch.object(
                agent,
                "candidate_support_region_signature",
                return_value="floor",
            ),
            mock.patch.object(
                agent,
                "route_corridor_class_signature",
                side_effect=lambda candidate, _container: (
                    f"corridor-{float(candidate.center[0]):.1f}"
                ),
            ),
        ):
            value = agent.evaluate_future_option_value(
                observation,
                pool,
                placed,
                probes,
                validation_budget=3,
            )

        self.assertEqual(value.route_baseline_candidates, 3)
        self.assertEqual(value.route_survived_candidates, 1)
        self.assertEqual(value.route_lost_candidates, 1)
        self.assertEqual(value.space_lost_candidates, 1)
        self.assertEqual(value.route_baseline_items, 3)
        self.assertEqual(value.route_survived_items, 1)
        self.assertEqual(value.route_baseline_item_orientations, 3)
        self.assertEqual(value.route_survived_item_orientations, 1)
        self.assertEqual(value.route_baseline_corridor_classes, 3)
        self.assertEqual(value.route_survived_corridor_classes, 1)
        self.assertEqual(value.route_lost_corridor_classes, 1)
        self.assertAlmostEqual(value.route_survival_share, 1.0 / 3.0)
        self.assertAlmostEqual(value.route_item_survival_share, 1.0 / 3.0)
        self.assertAlmostEqual(value.route_volume_survival_share, 1.0 / 3.0)
        self.assertAlmostEqual(value.route_blocked_item_volume_sum, 0.008)

    def test_structural_rejection_excludes_corridor(self):
        target = container()
        candidate = decision(1.0, 0).candidate

        with mock.patch.object(
            agent.Geometry,
            "transport_path_clear",
            return_value=False,
        ) as transport:
            reason = agent.Geometry.structural_rejection_reason(
                candidate,
                target,
            )

        self.assertIsNone(reason)
        transport.assert_not_called()

    def test_regular_and_release_rejection_keep_support_contract(self):
        target = container()
        regular = decision(1.0, 0).candidate
        release = agent.AABB(
            regular.center,
            regular.size,
            "release_candidate",
        )

        with (
            mock.patch.object(
                agent.Geometry,
                "has_stable_support",
                return_value=False,
            ),
            mock.patch.object(
                agent.Geometry,
                "transport_path_clear",
                return_value=True,
            ),
        ):
            self.assertEqual(
                agent.Geometry.rejection_reason(regular, target),
                "support",
            )
            self.assertIsNone(
                agent.Geometry.release_rejection_reason(release, target)
            )

    def test_route_survival_detects_real_transport_only_blockage(self):
        baseline = container()
        after = copy.deepcopy(baseline)
        blocking_item = item(0)
        blocking_item["pos"] = [0.0, -0.3, 0.12]
        blocking_item["orientation"] = 0
        after["packed_items"].append(blocking_item)
        target = decision(1.0, 1)
        target = agent.PlacementDecision(
            action=target.action,
            candidate=agent.AABB(
                center=(0.0, 0.5, 0.12),
                size=(0.2, 0.2, 0.2),
                name="settled_candidate",
            ),
            score=target.score,
        )

        value = agent.evaluate_route_survival_value(
            [baseline],
            [after],
            [item(0), item(1)],
            placed_pool_index=0,
            probe_decisions=[target],
            validation_budget=1,
        )

        self.assertEqual(value.baseline_candidates, 1)
        self.assertEqual(value.route_lost_candidates, 1)
        self.assertEqual(value.space_lost_candidates, 0)
        self.assertEqual(value.survived_candidates, 0)
        self.assertAlmostEqual(value.blocked_item_volume_sum, 0.008)

    def test_route_survival_incrementally_checks_only_new_placement(self):
        baseline = container()
        after = copy.deepcopy(baseline)
        placed_candidate = agent.AABB(
            center=(0.0, -0.3, 0.12),
            size=(0.2, 0.2, 0.2),
            name="settled_candidate",
        )
        placed_trace = agent.PlacementTrace(
            item_index=0,
            container_idx=0,
            orientation=0,
            candidate=placed_candidate,
            support=agent.SupportMetrics(1.0, 1.0, 1, 1.0),
            mass=1.0,
        )
        target = decision(1.0, 1)
        target = agent.PlacementDecision(
            action=target.action,
            candidate=agent.AABB(
                center=(0.0, 0.5, 0.12),
                size=(0.2, 0.2, 0.2),
                name="settled_candidate",
            ),
            score=target.score,
        )

        with mock.patch.object(
            agent.Geometry,
            "transport_path_clear",
        ) as full_transport:
            value = agent.evaluate_route_survival_value(
                [baseline],
                [after],
                [item(0), item(1)],
                placed_pool_index=0,
                probe_decisions=[target],
                validation_budget=1,
                placed_trace=placed_trace,
            )

        full_transport.assert_not_called()
        self.assertEqual(value.route_lost_candidates, 1)
        self.assertEqual(value.affected_transport_candidates, 1)
        self.assertEqual(value.unaffected_transport_candidates, 0)

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
        self.assertEqual(value.feasible_item_classes, 1)
        self.assertEqual(value.feasible_pose_classes, 1)
        self.assertGreater(value.distinct_corridor_classes, 0)
        self.assertGreater(value.distinct_action_classes, 0)
        self.assertAlmostEqual(value.max_feasible_item_volume, 0.008)
        self.assertGreaterEqual(value.greedy_packable_count, 1)
        self.assertGreater(value.greedy_packable_volume, 0.0)

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
                return_value=(
                    [q_best, resilient],
                    [q_best, resilient],
                    [q_best, resilient],
                ),
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
