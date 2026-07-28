import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

import numpy as np


AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("clean_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


def sample_container(
    require_shelf=True,
    center_x=2.5,
    cut_x=0.44,
    is_prioritized=False,
):
    return {
        "length": 2.0,
        "width": 1.45,
        "height": 1.61,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": cut_x,
        "require_shelf": require_shelf,
        "is_prioritized": is_prioritized,
        "center": [center_x, 0.0, 0.0],
        "packed_items": [],
    }


def sample_item(
    index,
    length=0.3,
    width=0.25,
    height=0.2,
    mass=5,
    is_soft=False,
    is_prioritized=False,
):
    return {
        "index": index,
        "length": length,
        "width": width,
        "height": height,
        "mass": mass,
        "is_soft": is_soft,
        "is_prioritized": is_prioritized,
    }


def halfspace_container(lower_point, lower_normal):
    container = sample_container(
        require_shelf=False,
        center_x=0.0,
        cut_x=0.0,
    )
    container["height"] = 1.0
    container["thickness"] = 0.0
    container["points"] = [
        [-1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, -0.725, 0.0],
        [0.0, 0.725, 0.0],
        [0.0, 0.0, 1.0],
        list(lower_point),
    ]
    container["n_vecs"] = [
        [-1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        list(lower_normal),
    ]
    return container


class GeometryContractTests(unittest.TestCase):
    def test_float32_action_preserves_more_than_official_5mm_inclusion_margin(self):
        transmitted_margin = float(np.float32(agent.INCLUSION_CLEARANCE))

        self.assertGreater(transmitted_margin, 0.015)
        self.assertAlmostEqual(
            agent.INCLUSION_CLEARANCE,
            agent.OFFICIAL_INCLUSION_CLEARANCE
            + agent.PHYSICS_BOUNDARY_GUARD
            + agent.FLOAT32_CLEARANCE_GUARD,
        )

    def test_float32_transport_clearance_preserves_official_15mm_margin(self):
        transmitted_clearance = float(np.float32(agent.TRANSPORT_CLEARANCE))

        self.assertGreater(transmitted_clearance, 0.015)
        self.assertAlmostEqual(
            agent.TRANSPORT_CLEARANCE,
            agent.OFFICIAL_TRANSPORT_CLEARANCE
            + agent.FLOAT32_CLEARANCE_GUARD,
        )

    def test_coordinate_round_trip_only_offsets_world_x(self):
        container = sample_container(center_x=5.0)
        local = np.array([-0.25, 0.4, 0.7])
        world = agent.local_to_world(local, container)
        np.testing.assert_allclose(world, [4.75, 0.4, 0.7])
        np.testing.assert_allclose(agent.world_to_local(world, container), local)

    def test_packed_dimensions_use_settled_quaternion(self):
        half_angle = np.pi / 8.0
        packed = {
            "length": 0.4,
            "width": 0.2,
            "height": 0.1,
            "orientation": 0,
            "orn": [0.0, 0.0, np.sin(half_angle), np.cos(half_angle)],
        }

        expected_xy = np.sqrt(0.5) * (0.4 + 0.2)
        np.testing.assert_allclose(
            agent.packed_dimensions(packed),
            [expected_xy, expected_xy, 0.1],
        )

    def test_shelf_boxes_are_derived_from_simulator_dimensions(self):
        shelves = {box.name: box for box in agent.shelf_aabbs(sample_container())}
        small = shelves["small_shelf"]
        main = shelves["main_shelf"]

        np.testing.assert_allclose(small.center, [-0.74, 0.0, 0.825])
        np.testing.assert_allclose(small.size, [0.44, 1.37, 0.04])
        np.testing.assert_allclose(main.center, [0.0, 0.3625, 0.825])
        np.testing.assert_allclose(main.size, [1.96, 0.645, 0.04])

    def test_official_shelf_key_is_supported(self):
        container = sample_container()
        container["shelf"] = container.pop("require_shelf")
        shelves = {box.name for box in agent.shelf_aabbs(container)}
        self.assertIn("main_shelf", shelves)

    def test_shelf_transport_sweep_uses_lifted_action_plus_start_height(self):
        container = sample_container()
        main = next(
            box for box in agent.shelf_aabbs(container)
            if box.name == "main_shelf"
        )
        item_height = 0.24
        center_z = main.top + item_height / 2
        self.assertAlmostEqual(center_z, 0.965)
        self.assertAlmostEqual(agent.SIMULATOR_DROP_HEIGHT, 0.08)
        candidate = agent.AABB((0.0, 0.0, center_z), (0.3, 0.3, item_height))
        sweep = agent.transport_sweep(candidate, container)
        self.assertAlmostEqual(
            sweep.center[2],
            center_z
            + agent.SHELF_ACTION_LIFT
            + agent.SIMULATOR_DROP_HEIGHT,
        )

    def test_floor_direct_rest_transport_stays_at_contact_height(self):
        container = sample_container(require_shelf=False, cut_x=0.0)
        item_height = 0.2
        center_z = container["thickness"] + item_height / 2.0
        candidate = agent.AABB(
            (0.0, 0.0, center_z),
            (0.3, 0.3, item_height),
        )

        sweep = agent.transport_sweep(candidate, container)

        self.assertAlmostEqual(sweep.center[2], center_z)

    def test_empty_container_corridor_is_clear_at_front_center_and_back(self):
        container = sample_container(require_shelf=False, cut_x=0.0)
        item_height = 0.2
        center_z = container["thickness"] + item_height / 2.0

        for target_y in (-0.45, 0.0, 0.45):
            with self.subTest(target_y=target_y):
                candidate = agent.AABB(
                    (0.0, target_y, center_z),
                    (0.3, 0.25, item_height),
                )
                self.assertTrue(
                    agent.Geometry.transport_path_clear(candidate, container)
                )

    def test_candidate_rejections_are_counted_by_reason(self):
        container = sample_container(require_shelf=False, cut_x=0.0)
        container["points"] = [
            [1.5, 0.0, 0.0],
            [3.5, 0.0, 0.0],
            [2.5, -0.725, 0.0],
            [2.5, 0.725, 0.0],
            [2.5, 0.0, 0.0],
            [2.5, 0.0, 1.61],
        ]
        container["n_vecs"] = [
            [-1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
            [0.0, 0.0, 1.0],
        ]
        observation = {"container_list": [container]}
        oversized = sample_item(
            7,
            length=3.0,
            width=0.25,
            height=0.2,
        )
        diagnostics = {}

        candidates = agent.CandidateGenerator.generate(
            observation,
            oversized,
            container_idx=0,
            orientation=0,
            diagnostics=diagnostics,
            item_idx=7,
        )

        self.assertEqual(candidates, [])
        self.assertEqual(diagnostics["total"]["attempted"], 0)
        self.assertEqual(diagnostics["total"]["accepted"], 0)
        self.assertGreater(
            diagnostics["total"]["envelope_pruned"],
            0,
        )
        self.assertEqual(
            diagnostics["by_item"]["7"]["attempted"],
            diagnostics["total"]["attempted"],
        )

    def test_z_interval_solves_sloped_lower_container_boundary(self):
        diagonal = 1.0 / np.sqrt(2.0)
        container = halfspace_container(
            lower_point=(0.0, 0.0, 0.0),
            lower_normal=(-diagonal, 0.0, -diagonal),
        )
        dims = (0.4, 0.2, 0.2)

        interval = agent.container_z_interval(
            x=0.0,
            y=0.0,
            dims=dims,
            container=container,
        )

        self.assertIsNotNone(interval)
        expected_minimum = 0.3 + agent.INCLUSION_CLEARANCE / diagonal
        self.assertAlmostEqual(interval[0], expected_minimum, places=5)
        candidate = agent.AABB(
            (0.0, 0.0, interval[0] + 1e-5),
            dims,
            "release_candidate",
        )
        self.assertTrue(agent.Geometry.inside_container(candidate, container))

    def test_release_candidate_is_generated_without_analytic_support(self):
        container = halfspace_container(
            lower_point=(0.0, 0.0, 0.3),
            lower_normal=(0.0, 0.0, -1.0),
        )
        observation = {"container_list": [container]}
        item = sample_item(8, length=0.4, width=0.2, height=0.2)
        diagnostics = {}

        candidates = agent.CandidateGenerator.generate(
            observation,
            item,
            container_idx=0,
            orientation=0,
            diagnostics=diagnostics,
            item_idx=8,
        )

        self.assertTrue(candidates)
        self.assertTrue(
            all(candidate.name == "release_candidate" for candidate in candidates)
        )
        self.assertEqual(
            agent.Geometry.support_ratio(candidates[0], container),
            0.0,
        )
        self.assertIsNone(
            agent.Geometry.release_rejection_reason(candidates[0], container)
        )
        np.testing.assert_allclose(
            agent.simulator_action_center(candidates[0], container),
            candidates[0].center,
        )
        settled_proxy = agent.settled_proxy_candidate(
            candidates[0],
            container,
        )
        self.assertLess(settled_proxy.center[2], candidates[0].center[2])
        self.assertTrue(
            agent.Geometry.inside_container(settled_proxy, container)
        )
        self.assertGreater(
            diagnostics["by_kind"]["release"]["accepted"],
            0,
        )

    def test_transport_sweeps_include_official_y_then_x_legs(self):
        container = sample_container()
        candidate = agent.AABB((-0.8, 0.25, 1.0), (0.3, 0.2, 0.2))

        sweeps = agent.transport_sweeps(candidate, container)

        self.assertEqual(len(sweeps), 2)
        y_leg, x_leg = sweeps
        expected_start_x = -0.36
        self.assertAlmostEqual(y_leg.center[0], expected_start_x)
        self.assertAlmostEqual(x_leg.minimum[0], -0.95)
        self.assertAlmostEqual(x_leg.maximum[0], expected_start_x + 0.15)

    def test_shelf_action_target_is_lifted_above_direct_rest_threshold(self):
        container = sample_container()
        main = next(
            box for box in agent.shelf_aabbs(container)
            if box.name == "main_shelf"
        )
        candidate = agent.AABB(
            (0.0, 0.35, main.top + 0.12),
            (0.3, 0.3, 0.24),
        )

        action_center = agent.simulator_action_center(candidate, container)
        action_bottom = float(action_center[2]) - candidate.size[2] / 2.0

        self.assertAlmostEqual(candidate.minimum[2], main.top)
        self.assertGreater(action_bottom - main.top, 0.05)

    def test_lateral_clearance_guards_15mm_and_allows_vertical_contact(self):
        obstacle = agent.AABB((0.0, 0.0, 0.2), (0.4, 0.4, 0.4))
        too_close = agent.AABB((0.415, 0.0, 0.2), (0.4, 0.4, 0.4))
        clear = agent.AABB((0.416, 0.0, 0.2), (0.4, 0.4, 0.4))
        stacked = agent.AABB((0.0, 0.0, 0.6), (0.4, 0.4, 0.4))

        self.assertTrue(
            agent.penetrates_with_lateral_clearance(
                too_close, obstacle, agent.TRANSPORT_CLEARANCE
            )
        )
        self.assertFalse(
            agent.penetrates_with_lateral_clearance(
                clear, obstacle, agent.TRANSPORT_CLEARANCE
            )
        )
        self.assertFalse(
            agent.penetrates_with_lateral_clearance(
                stacked, obstacle, agent.TRANSPORT_CLEARANCE
            )
        )

    def test_transport_clearance_uses_3d_closest_distance(self):
        obstacle = agent.AABB((0.0, 0.0, 0.2), (0.4, 0.4, 0.4))
        vertically_close = agent.AABB((0.0, 0.0, 0.61), (0.4, 0.4, 0.4))
        vertically_clear = agent.AABB((0.0, 0.0, 0.617), (0.4, 0.4, 0.4))

        self.assertTrue(
            agent.within_euclidean_clearance(
                vertically_close,
                obstacle,
                agent.TRANSPORT_CLEARANCE,
            )
        )
        self.assertFalse(
            agent.within_euclidean_clearance(
                vertically_clear,
                obstacle,
                agent.TRANSPORT_CLEARANCE,
            )
        )

    def test_shelf_top_is_support_but_mid_shelf_is_collision(self):
        container = sample_container()
        main = next(
            box for box in agent.shelf_aabbs(container)
            if box.name == "main_shelf"
        )
        dims = (0.4, 0.3, 0.2)
        on_top = agent.AABB(
            (
                0.0,
                0.35,
                main.top + dims[2] / 2,
            ),
            dims,
        )
        through_shelf = agent.AABB((0.0, 0.35, main.center[2]), dims)

        self.assertTrue(agent.Geometry.clears_static_geometry(on_top, container))
        self.assertGreaterEqual(
            agent.Geometry.support_ratio(on_top, container),
            agent.MIN_SUPPORT_RATIO,
        )
        self.assertFalse(
            agent.Geometry.clears_static_geometry(through_shelf, container)
        )

    def test_floating_item_is_rejected(self):
        container = sample_container(require_shelf=False)
        floating = agent.AABB((0.4, -0.4, 0.6), (0.3, 0.3, 0.2))
        self.assertFalse(agent.Geometry.has_stable_support(floating, container))

    def test_soft_and_priority_items_are_not_future_support_surfaces(self):
        container = sample_container(require_shelf=False, cut_x=0.0)
        base = {
            "pos": [2.5, 0.0, 0.24],
            "length": 0.4,
            "width": 0.4,
            "height": 0.4,
            "orientation": 0,
        }
        container["packed_items"] = [
            {**base, "is_soft": True, "is_prioritized": False},
            {
                **base,
                "pos": [2.9, 0.0, 0.24],
                "is_soft": False,
                "is_prioritized": True,
            },
        ]
        names = [surface.name for surface in agent.support_surfaces(container)]
        self.assertEqual(names, ["floor"])

    def test_support_plane_components_merge_only_coplanar_edge_neighbors(self):
        left = agent.AABB(
            (-0.105, 0.0, 0.24),
            (0.2, 0.4, 0.4),
            "packed_item",
        )
        near_right = agent.AABB(
            (0.105, 0.0, 0.24),
            (0.2, 0.4, 0.4),
            "packed_item",
        )
        far_right = agent.AABB(
            (0.125, 0.0, 0.24),
            (0.2, 0.4, 0.4),
            "packed_item",
        )
        diagonal = agent.AABB(
            (0.105, 0.41, 0.24),
            (0.2, 0.4, 0.4),
            "packed_item",
        )

        merged = agent.support_plane_components(
            [left, near_right],
            adjacency=0.016,
        )
        separated = agent.support_plane_components(
            [left, far_right],
            adjacency=0.016,
        )
        corner_only = agent.support_plane_components(
            [left, diagonal],
            adjacency=0.016,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].surfaces), 2)
        self.assertEqual(len(separated), 2)
        self.assertEqual(len(corner_only), 2)

    def test_rectangle_union_area_does_not_double_count_overlap(self):
        area = agent.rectangle_union_area(
            [
                (0.0, 1.0, 0.0, 1.0),
                (0.5, 1.5, 0.0, 1.0),
            ]
        )

        self.assertAlmostEqual(area, 1.5)

    def test_support_plane_priority_is_floor_area_depth_then_height(self):
        floor = agent.SupportPlaneComponent(
            (
                agent.AABB(
                    (0.0, 0.0, 0.04),
                    (2.0, 1.45, 0.0),
                    "floor",
                ),
            )
        )
        large = agent.SupportPlaneComponent(
            (agent.AABB((0.0, 0.0, 0.6), (0.8, 0.8, 0.2)),)
        )
        deep = agent.SupportPlaneComponent(
            (agent.AABB((0.0, 0.4, 0.5), (0.5, 0.5, 0.2)),)
        )
        front_low = agent.SupportPlaneComponent(
            (agent.AABB((0.0, -0.4, 0.3), (0.5, 0.5, 0.2)),)
        )

        ordered = agent.order_support_plane_components(
            [front_low, deep, large, floor]
        )

        self.assertEqual(ordered, [floor, large, deep, front_low])

    def test_connected_support_plane_accepts_bridge_support(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        base = {
            "length": 0.2,
            "width": 0.4,
            "height": 0.4,
            "orientation": 0,
            "is_soft": False,
            "is_prioritized": False,
        }
        container["packed_items"] = [
            {**base, "pos": [-0.105, 0.0, 0.24]},
            {**base, "pos": [0.105, 0.0, 0.24]},
        ]
        bridge = agent.AABB(
            (0.0, 0.0, 0.54),
            (0.4, 0.4, 0.2),
            "candidate",
        )

        ratio = agent.Geometry.support_ratio(bridge, container)

        self.assertAlmostEqual(ratio, 0.975)
        self.assertTrue(agent.Geometry.has_stable_support(bridge, container))

    def test_support_plane_diagnostics_compare_connected_and_separate_counts(
        self,
    ):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        base = {
            "length": 0.2,
            "width": 0.3,
            "height": 0.4,
            "orientation": 0,
            "is_soft": False,
            "is_prioritized": False,
        }
        container["packed_items"] = [
            {**base, "pos": [-0.105, -0.05, 0.24]},
            {**base, "pos": [0.105, 0.05, 0.24]},
        ]
        observation = {"container_list": [container]}
        item = sample_item(8, length=0.4, width=0.3, height=0.2)
        diagnostics = {}

        candidates = [
            candidate
            for candidate in agent.CandidateGenerator.iter_attempts(
                observation,
                item,
                container_idx=0,
                orientation=0,
                diagnostics=diagnostics,
                item_idx=8,
                attempt_kind="settled",
                generator_mode="support_plane",
            )
            if candidate is not None
        ]

        event = diagnostics["support_plane_searches"][0]
        self.assertEqual(event["surface_count"], 3)
        self.assertEqual(event["component_count"], 2)
        self.assertNotEqual(
            event["connected_anchor_count"],
            event["unconnected_anchor_count"],
        )
        self.assertAlmostEqual(event["adjacency_threshold"], 0.016)
        self.assertTrue(
            any(
                abs(candidate.center[0]) <= agent.EPS
                and abs(candidate.minimum[2] - 0.44) <= agent.CONTACT_TOLERANCE
                for candidate in candidates
            )
        )

    def test_offline_order_places_hard_items_before_soft_and_priority(self):
        items = [
            {
                "index": 0,
                "length": 0.4,
                "width": 0.4,
                "height": 0.4,
                "mass": 10,
                "is_soft": False,
                "is_prioritized": True,
            },
            {
                "index": 1,
                "length": 0.4,
                "width": 0.4,
                "height": 0.4,
                "mass": 8,
                "is_soft": True,
                "is_prioritized": False,
            },
            {
                "index": 2,
                "length": 0.5,
                "width": 0.5,
                "height": 0.4,
                "mass": 15,
                "is_soft": False,
                "is_prioritized": False,
            },
        ]
        result = agent.Agent("").optimize(items)
        self.assertEqual(result, [2, 1, 0])

    def test_priority_item_is_routed_to_priority_container(self):
        priority_item = {
            "index": 9,
            "length": 0.3,
            "width": 0.3,
            "height": 0.2,
            "mass": 5,
            "is_soft": False,
            "is_prioritized": True,
        }
        observation = {
            "pool_list": [priority_item],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                    is_prioritized=False,
                ),
                sample_container(
                    require_shelf=False,
                    center_x=2.5,
                    cut_x=0.0,
                    is_prioritized=True,
                ),
            ],
        }
        action = agent.Agent("").policy(observation)
        self.assertEqual(action["container_idx"], 1)


class LookaheadSelectionTests(unittest.TestCase):
    @staticmethod
    def decision(score, item_idx=0):
        return agent.PlacementDecision(
            action={
                "item_idx": item_idx,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB((0.0, 0.0, 0.1), (0.2, 0.2, 0.2)),
            score=score,
        )

    def test_weighted_mode_preserves_existing_discounted_sum(self):
        evaluation = agent.LookaheadEvaluation(
            decision=self.decision(10.0),
            feasible_next_items=1,
            total_next_items=2,
            best_next_score=4.0,
        )

        self.assertEqual(
            agent.lookahead_rank_key(
                evaluation,
                mode="weighted",
                discount=0.5,
            ),
            (12.0,),
        )

    def test_depth2_mode_prefers_a_feasible_next_step_without_score_mixing(self):
        dead_end = agent.LookaheadEvaluation(
            decision=self.decision(100.0),
            feasible_next_items=0,
            total_next_items=1,
            best_next_score=0.0,
        )
        viable = agent.LookaheadEvaluation(
            decision=self.decision(1.0),
            feasible_next_items=1,
            total_next_items=1,
            best_next_score=-10.0,
        )

        self.assertGreater(
            agent.lookahead_rank_key(viable, mode="depth2"),
            agent.lookahead_rank_key(dead_end, mode="depth2"),
        )

    def test_pool_resilience_mode_prefers_more_placeable_visible_items(self):
        narrow = agent.LookaheadEvaluation(
            decision=self.decision(50.0),
            feasible_next_items=1,
            total_next_items=3,
            best_next_score=20.0,
        )
        resilient = agent.LookaheadEvaluation(
            decision=self.decision(2.0),
            feasible_next_items=2,
            total_next_items=3,
            best_next_score=1.0,
        )

        self.assertGreater(
            agent.lookahead_rank_key(resilient, mode="pool_resilience"),
            agent.lookahead_rank_key(narrow, mode="pool_resilience"),
        )

    def test_visible_pool_feasibility_uses_real_placement_core(self):
        valid_item = sample_item(0, length=0.2, width=0.2, height=0.2)
        oversized_item = sample_item(1, length=5.0, width=5.0, height=5.0)
        observation = {
            "pool_list": [valid_item, oversized_item],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }

        result = agent.evaluate_visible_pool_feasibility(
            observation,
            [(0, valid_item), (1, oversized_item)],
            deadline=time.perf_counter() + 2.0,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.feasible_items, 1)
        self.assertEqual(result.evaluated_items, 2)
        self.assertGreater(result.best_score, 0.0)

    def test_unknown_lookahead_mode_is_rejected(self):
        evaluation = agent.LookaheadEvaluation(
            decision=self.decision(1.0),
            feasible_next_items=0,
            total_next_items=0,
            best_next_score=0.0,
        )

        with self.assertRaises(ValueError):
            agent.lookahead_rank_key(evaluation, mode="not-a-mode")

    def test_pool_of_40_stays_below_online_time_limit(self):
        template = {
            "length": 0.3,
            "width": 0.25,
            "height": 0.2,
            "mass": 5,
            "is_soft": False,
            "is_prioritized": False,
        }
        observation = {
            "pool_list": [
                {**template, "index": index} for index in range(40)
            ],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        started = time.perf_counter()
        action = agent.Agent("").policy(observation)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, agent.POLICY_BUDGET_SECONDS)
        self.assertIn(action["item_idx"], range(40))

    def test_candidate_attempt_iterator_stops_inside_an_orientation(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        observation = {"container_list": [container]}
        item = sample_item(0)
        diagnostics = {}

        class TickingClock:
            def __init__(self):
                self.value = 0.0

            def __call__(self):
                self.value += 1.0
                return self.value

        clock = TickingClock()
        with mock.patch.object(agent.time, "perf_counter", side_effect=clock):
            attempts = list(
                agent.CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    container_idx=0,
                    orientation=0,
                    deadline=4.0,
                    diagnostics=diagnostics,
                    item_idx=0,
                )
            )

        self.assertLessEqual(clock.value, 5.0)
        self.assertLess(len(attempts), 10)

    def test_shallow_pass_reaches_later_item_before_exhausting_first(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        first_item = sample_item(0, length=0.2, width=0.2, height=0.2)
        second_item = sample_item(1, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [first_item, second_item],
            "container_list": [container],
        }
        later_candidate = agent.AABB(
            (0.3, 0.0, 0.14),
            (0.2, 0.2, 0.2),
        )

        def attempts(
            _observation,
            _item,
            _container_idx,
            _orientation,
            **kwargs,
        ):
            if kwargs["item_idx"] == 0:
                for _ in range(agent.ANCHOR_FIRST_PASS_ATTEMPTS + 10):
                    yield None
                return
            yield later_candidate

        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent.Ranker, "score", return_value=7.0),
        ):
            decision = agent.PlacementCore.choose(
                observation,
                [(0, first_item), (1, second_item)],
            )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action["item_idx"], 1)
        self.assertEqual(decision.score, 7.0)

    def test_candidate_audit_separates_settled_and_release_candidates(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(7, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        settled = agent.AABB(
            (0.1, 0.2, 0.14),
            (0.2, 0.2, 0.2),
            "candidate",
        )
        release = agent.AABB(
            (0.1, 0.2, 0.2),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] == "settled":
                yield settled
            else:
                yield release

        diagnostics = {}
        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent, "CANDIDATE_AUDIT_ENABLED", True),
        ):
            candidates = list(
                agent.iter_prioritized_candidates(
                    observation,
                    [(0, item)],
                    diagnostics=diagnostics,
                )
            )

        self.assertGreater(len(candidates), 1)
        searches = diagnostics["candidate_audit"]
        self.assertEqual(len(searches), 1)
        records = searches[0]["accepted_settled"]
        release_records = searches[0]["accepted_release"]
        self.assertTrue(records)
        self.assertTrue(release_records)
        self.assertTrue(
            all(record["kind"] == "candidate" for record in records)
        )
        self.assertTrue(
            all(
                record["kind"] == "release_candidate"
                for record in release_records
            )
        )
        self.assertEqual(records[0]["item_index"], 7)
        self.assertEqual(records[0]["pool_index"], 0)
        self.assertEqual(records[0]["action_center"], [0.1, 0.2, 0.14])
        self.assertIn("elapsed_seconds", records[0])

    def test_candidate_audit_is_absent_by_default(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(7, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        diagnostics = {}
        with mock.patch.object(agent, "CANDIDATE_AUDIT_ENABLED", False):
            next(
                agent.iter_prioritized_candidates(
                    observation,
                    [(0, item)],
                    diagnostics=diagnostics,
                )
            )
        self.assertNotIn("candidate_audit", diagnostics)

    def test_priority_ordered_search_keeps_best_validated_incumbent(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(0, length=0.6, width=0.4, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        visited_orientations = []

        def attempts(
            _observation,
            _item,
            _container_idx,
            orientation,
            **_kwargs,
        ):
            visited_orientations.append(orientation)
            dims = agent.get_rotated_dimensions(
                item["length"],
                item["width"],
                item["height"],
                orientation,
            )
            yield agent.AABB(
                (float(orientation), 0.0, 0.2),
                dims,
            )

        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(
                agent.Ranker,
                "score",
                side_effect=lambda candidate, *_args: candidate.center[0],
            ),
        ):
            decision = agent.PlacementCore.choose(
                observation,
                [(0, item)],
            )

        first_dims = agent.get_rotated_dimensions(
            item["length"],
            item["width"],
            item["height"],
            visited_orientations[0],
        )
        maximum_base = max(
            np.prod(
                agent.get_rotated_dimensions(
                    item["length"],
                    item["width"],
                    item["height"],
                    orientation,
                )[:2]
            )
            for orientation in agent.unique_orientations(item)
        )
        self.assertAlmostEqual(first_dims[0] * first_dims[1], maximum_base)
        self.assertEqual(
            decision.score,
            max(float(orientation) for orientation in visited_orientations),
        )

    def test_deadline_returns_best_validated_incumbent(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(0, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        safe_candidate = agent.AABB(
            (0.0, 0.0, 0.14),
            (0.2, 0.2, 0.2),
        )

        def attempts(*_args, **_kwargs):
            yield safe_candidate
            while True:
                yield None

        started = time.perf_counter()
        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent.Ranker, "score", return_value=3.0),
        ):
            decision = agent.PlacementCore.choose(
                observation,
                [(0, item)],
                deadline=started + 0.02,
            )
        elapsed = time.perf_counter() - started

        self.assertIsNotNone(decision)
        self.assertEqual(decision.score, 3.0)
        self.assertLess(elapsed, 0.2)

    def test_release_probe_is_not_hidden_behind_settled_exhaustion(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(0, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        release_candidate = agent.AABB(
            (0.0, 0.0, 0.2),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )
        visited_kinds = []

        def attempts(*_args, **kwargs):
            attempt_kind = kwargs["attempt_kind"]
            visited_kinds.append(attempt_kind)
            if attempt_kind == "settled":
                for _ in range(agent.ANCHOR_FIRST_PASS_ATTEMPTS + 10):
                    yield None
                return
            yield release_candidate

        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent.Ranker, "score", return_value=5.0),
        ):
            decision = agent.PlacementCore.choose(
                observation,
                [(0, item)],
            )

        self.assertEqual(visited_kinds[:2], ["settled", "release"])
        self.assertIsNotNone(decision)
        self.assertEqual(decision.candidate.name, "release_candidate")

    def test_settled_candidate_is_preferred_over_higher_scoring_release(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(0, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        settled_candidate = agent.AABB(
            (0.0, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "settled_candidate",
        )
        release_candidate = agent.AABB(
            (0.0, 0.0, 0.2),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] == "release":
                yield release_candidate
            else:
                yield settled_candidate

        def score(candidate, *_args):
            return 10.0 if candidate.name == "release_candidate" else 1.0

        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent.Ranker, "score", side_effect=score),
        ):
            decision = agent.PlacementCore.choose(
                observation,
                [(0, item)],
            )
            candidates = agent.PlacementCore.top_candidates(
                observation,
                [(0, item)],
                k=3,
            )

        self.assertEqual(decision.candidate.name, "settled_candidate")
        self.assertTrue(candidates)
        self.assertTrue(
            all(
                candidate.candidate.name == "settled_candidate"
                for candidate in candidates
            )
        )

    def test_policy_trace_separates_predicted_residual_from_action(self):
        observation = {
            "pool_list": [
                sample_item(0, length=0.2, width=0.2, height=0.2),
                sample_item(1, length=0.2, width=0.2, height=0.2),
            ],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "policy.jsonl"
            with mock.patch.dict(
                os.environ,
                {"NEDO_POLICY_TRACE_PATH": str(trace_path)},
            ):
                solver = agent.Agent("")
                solver.get_init_states(
                    {
                        "optimize": False,
                        "lookahead_k": 2,
                        "container_list": observation["container_list"],
                    }
                )
                solver.policy(observation)

            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(events[0]["event"], "init")
        self.assertEqual(events[1]["event"], "decision")
        self.assertEqual(events[1]["evaluated_remaining_items"], 1)
        self.assertIn("feasible_remaining_ratio", events[1])
        self.assertIn(events[1]["selected_item_index"], {0, 1})
        self.assertEqual(events[1]["action_source"], "placement_core")
        self.assertGreater(
            events[1]["candidate_diagnostics"]["total"]["attempted"],
            0,
        )

    def test_fixed_fallback_is_included_in_policy_trace(self):
        observation = {
            "pool_list": [sample_item(9)],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "policy.jsonl"
            with (
                mock.patch.dict(
                    os.environ,
                    {"NEDO_POLICY_TRACE_PATH": str(trace_path)},
                ),
                mock.patch.object(
                    agent.PlacementCore,
                    "top_candidates",
                    return_value=[],
                ),
                mock.patch.object(
                    agent.PlacementCore,
                    "choose",
                    return_value=None,
                ),
            ):
                solver = agent.Agent("")
                solver.get_init_states(
                    {
                        "optimize": False,
                        "lookahead_k": 1,
                        "container_list": observation["container_list"],
                    }
                )
                action = solver.policy(observation)

            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(action["place_pos"].tolist(), [0.0, 0.0, 0.25])
        self.assertEqual(events[1]["action_source"], "fixed_fallback")
        self.assertEqual(events[1]["selected_item_index"], 9)
        self.assertEqual(solver.last_action_source, "fixed_fallback")
        self.assertEqual(solver.last_candidate_kind, "fixed_fallback")


class OfflineOptimizationTests(unittest.TestCase):
    def test_pair_macro_records_executable_order_layout_and_signature(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        items = [
            sample_item(0, length=0.4, width=0.3, height=0.2, mass=7),
            sample_item(1, length=0.35, width=0.3, height=0.2, mass=6),
        ]

        macros = agent.generate_pair_block_templates(items, [container])

        self.assertGreaterEqual(len(macros), 1)
        by_order = {macro.internal_order: macro for macro in macros}
        self.assertIn((0, 1), by_order)
        self.assertIn((1, 0), by_order)
        macro = by_order[(0, 1)]
        self.assertEqual(macro.item_indices, (0, 1))
        self.assertEqual(len(macro.relative_placements), 2)
        self.assertEqual(len(macro.dimensions), 3)
        self.assertGreater(macro.signature.fill_ratio, 0.0)
        self.assertGreaterEqual(
            macro.signature.min_support_ratio,
            agent.MIN_SUPPORT_RATIO,
        )

    def test_pair_macro_neighbor_keeps_internal_order_and_permutation(self):
        items = [sample_item(index) for index in range(5)]
        macro = agent.BlockTemplate(
            item_indices=(1, 2),
            internal_order=(1, 2),
            relative_placements=(),
            dimensions=(0.6, 0.3, 0.2),
            signature=agent.BlockSignature(
                fill_ratio=0.8,
                top_profile=(),
                min_support_ratio=1.0,
                total_mass=10.0,
                center_of_mass=(0.3, 0.15, 0.1),
            ),
        )

        neighbor = agent.apply_block_template_neighbor(
            items,
            macro,
            target_position=4,
        )
        indices = [item["index"] for item in neighbor]

        self.assertEqual(set(indices), {0, 1, 2, 3, 4})
        self.assertEqual(indices, [0, 3, 1, 2, 4])

    def test_init_states_keeps_clean_container_templates(self):
        solver = agent.Agent("")
        container = sample_container(require_shelf=False, center_x=0.0, cut_x=0.0)
        container["packed_items"] = [sample_item(99)]

        self.assertTrue(
            solver.get_init_states(
                {
                    "optimize": True,
                    "lookahead_k": 1,
                    "container_list": [container],
                }
            )
        )
        self.assertEqual(len(solver._container_templates), 1)
        self.assertEqual(solver._container_templates[0]["packed_items"], [])

    def test_dry_run_result_uses_failure_first_lexicographic_order(self):
        more_items = agent.DryRunResult(
            placed_count=2,
            failed_index=2,
            placed_volume=0.02,
            fill_ratio=0.01,
            stability_proxy=0.1,
            center_of_mass_z=1.0,
            normalized_center_of_mass_z=0.9,
            mean_support_ratio=0.6,
            min_support_ratio=0.55,
            min_support_margin=-0.5,
            mean_support_count=1.0,
            runtime_seconds=0.01,
        )
        prettier_but_failed_earlier = agent.DryRunResult(
            placed_count=1,
            failed_index=1,
            placed_volume=0.5,
            fill_ratio=0.9,
            stability_proxy=1.0,
            center_of_mass_z=0.1,
            normalized_center_of_mass_z=0.1,
            mean_support_ratio=1.0,
            min_support_ratio=1.0,
            min_support_margin=1.0,
            mean_support_count=3.0,
            runtime_seconds=0.01,
        )
        self.assertGreater(more_items.rank_key(), prettier_but_failed_earlier.rank_key())

    def test_dry_run_places_simple_sequence_with_common_core(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        container["volume"] = 4.0
        evaluator = agent.DryRunEvaluator([container])
        items = [sample_item(0), sample_item(1)]

        result = evaluator.evaluate(items)

        self.assertEqual(result.placed_count, 2)
        self.assertIsNone(result.failed_index)
        self.assertGreater(result.fill_ratio, 0.0)
        self.assertGreaterEqual(result.mean_support_ratio, agent.MIN_SUPPORT_RATIO)

    def test_optimize_is_deterministic_and_returns_a_permutation(self):
        solver = agent.Agent("")
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        container["volume"] = 4.0
        solver.get_init_states({"optimize": True, "container_list": [container]})
        solver._offline_search_budget_seconds = 0.05
        solver._offline_max_evaluations = 8
        items = [
            sample_item(0, length=0.45, width=0.3, mass=8),
            sample_item(1, length=0.3, width=0.25, mass=5),
            sample_item(2, length=0.4, width=0.3, mass=7),
        ]

        first = solver.optimize(items)
        second = solver.optimize(items)

        self.assertEqual(first, second)
        self.assertEqual(set(first), {0, 1, 2})

    def test_optimize_never_returns_worse_than_constructive_seed(self):
        solver = agent.Agent("")
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        container["volume"] = 4.0
        solver.get_init_states({"optimize": True, "container_list": [container]})
        solver._offline_search_budget_seconds = 0.2
        solver._offline_max_evaluations = 12
        items = [
            sample_item(0, length=0.45, width=0.3, height=0.25, mass=8),
            sample_item(1, length=0.3, width=0.25, height=0.2, mass=5),
            sample_item(2, length=0.4, width=0.3, height=0.22, mass=7),
            sample_item(3, length=0.35, width=0.28, height=0.2, mass=6),
        ]
        evaluator = agent.DryRunEvaluator([container])
        seed = agent.constructive_order(items)
        seed_result = evaluator.evaluate(seed)

        optimized_indices = solver.optimize(items)
        by_index = {item["index"]: item for item in items}
        optimized = [by_index[index] for index in optimized_indices]
        optimized_result = evaluator.evaluate(optimized)

        self.assertGreaterEqual(
            optimized_result.rank_key(),
            seed_result.rank_key(),
        )

    def test_optimize_generates_pair_macro_candidates(self):
        solver = agent.Agent("")
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        solver.get_init_states({"optimize": True, "container_list": [container]})
        solver._offline_search_budget_seconds = 0.2
        solver._offline_max_evaluations = 8
        items = [
            sample_item(0, length=0.4, width=0.3, height=0.2, mass=7),
            sample_item(1, length=0.35, width=0.3, height=0.2, mass=6),
            sample_item(2, length=0.3, width=0.25, height=0.2, mass=5),
        ]

        result = solver.optimize(items)

        self.assertEqual(set(result), {0, 1, 2})
        self.assertGreater(solver.last_pair_macro_candidates, 0)


if __name__ == "__main__":
    unittest.main()
