import copy
import importlib.util
import json
import math
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

    def test_support_plane_release_does_not_delegate_to_cartesian(self):
        container = halfspace_container(
            lower_point=(0.0, 0.0, 0.3),
            lower_normal=(0.0, 0.0, -1.0),
        )
        observation = {"container_list": [container]}
        item = sample_item(8, length=0.4, width=0.2, height=0.2)
        diagnostics = {}

        with mock.patch.object(
            agent.CandidateGenerator,
            "iter_cartesian_attempts",
            side_effect=AssertionError(
                "support-plane release must not scan Cartesian anchors"
            ),
        ):
            attempts = list(
                agent.CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    container_idx=0,
                    orientation=0,
                    diagnostics=diagnostics,
                    item_idx=8,
                    attempt_kind="release",
                    generator_mode="support_plane",
                )
            )
            fallback_candidates = agent.CandidateGenerator.generate(
                observation,
                item,
                container_idx=0,
                orientation=0,
                diagnostics={},
                item_idx=8,
                generator_mode="support_plane",
            )

        candidates = [
            candidate for candidate in attempts if candidate is not None
        ]
        self.assertTrue(candidates)
        self.assertTrue(fallback_candidates)
        self.assertTrue(
            all(
                candidate.name == "release_candidate"
                for candidate in fallback_candidates
            )
        )
        self.assertLessEqual(
            attempts.index(candidates[0]) + 1,
            agent.ANCHOR_FIRST_PASS_ATTEMPTS,
        )
        self.assertEqual(
            diagnostics["release_plane_searches"][0]["component_count"],
            len(
                agent.support_plane_components(
                    agent.support_surfaces(container)
                )
            ),
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

    def test_release_risk_features_separate_command_from_settled_proxy(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(21, length=0.4, width=0.2, height=0.2)
        release = agent.AABB(
            center=(0.0, 0.0, 0.04 + 0.1 + agent.RELEASE_TARGET_LIFT),
            size=(0.4, 0.2, 0.2),
            name="release_candidate",
        )

        features = agent.release_risk_features(
            release,
            item,
            container,
            orientation=0,
        )

        self.assertAlmostEqual(features.support_ratio, 1.0)
        self.assertAlmostEqual(features.overhang_ratio, 0.0)
        self.assertAlmostEqual(
            features.drop_normalized,
            agent.RELEASE_TARGET_LIFT / item["height"],
        )
        self.assertAlmostEqual(features.left_right_imbalance, 0.0)
        self.assertAlmostEqual(features.front_back_imbalance, 0.0)
        self.assertAlmostEqual(features.support_imbalance, 0.0)
        self.assertAlmostEqual(features.initial_tilt_deg, 0.0)
        self.assertEqual(
            features.feature_sources(),
            {
                "support_ratio": "predicted_contact_state",
                "com_margin": "predicted_contact_state",
                "overhang_ratio": "predicted_contact_state",
                "drop_normalized": (
                    "command_and_predicted_contact_state"
                ),
                "support_imbalance": "predicted_contact_state",
                "left_right_imbalance": "predicted_contact_state",
                "front_back_imbalance": "predicted_contact_state",
                "initial_tilt_deg": "command_state",
                "initial_orientation": "command_state",
            },
        )

    def test_release_risk_is_mirror_invariant_with_direction_sign_flip(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        base = {
            "length": 0.2,
            "width": 0.4,
            "height": 0.2,
            "mass": 10,
            "orientation": 0,
            "is_soft": False,
            "is_prioritized": False,
        }
        container["packed_items"] = [
            {**base, "pos": [-0.1, 0.0, 0.14]},
        ]
        mirrored = copy.deepcopy(container)
        mirrored["packed_items"][0]["pos"][0] *= -1.0
        item = sample_item(22, length=0.4, width=0.4, height=0.2)
        release = agent.AABB(
            center=(0.0, 0.0, 0.24 + 0.1 + agent.RELEASE_TARGET_LIFT),
            size=(0.4, 0.4, 0.2),
            name="release_candidate",
        )

        left = agent.release_risk_features(
            release, item, container, orientation=0
        )
        right = agent.release_risk_features(
            release, item, mirrored, orientation=0
        )
        left_assessment = agent.evaluate_release_risk(left)
        right_assessment = agent.evaluate_release_risk(right)

        self.assertAlmostEqual(left.support_ratio, right.support_ratio)
        self.assertAlmostEqual(left.com_margin, right.com_margin)
        self.assertAlmostEqual(left.overhang_ratio, right.overhang_ratio)
        self.assertAlmostEqual(left.drop_normalized, right.drop_normalized)
        self.assertAlmostEqual(left.initial_tilt_deg, right.initial_tilt_deg)
        self.assertEqual(left.initial_orientation, right.initial_orientation)
        self.assertAlmostEqual(
            left.support_imbalance, right.support_imbalance
        )
        self.assertAlmostEqual(
            left.left_right_imbalance,
            -right.left_right_imbalance,
        )
        self.assertAlmostEqual(
            left.front_back_imbalance,
            right.front_back_imbalance,
        )
        self.assertEqual(left_assessment.passed, right_assessment.passed)
        self.assertEqual(left_assessment.reasons, right_assessment.reasons)

    def test_initial_tilt_is_an_unavailable_placeholder_and_never_gates(self):
        self.assertIn(
            "initial_tilt_deg",
            agent.ReleaseRiskFeatures.unavailable_features(),
        )
        availability = agent.ReleaseRiskFeatures.feature_availability()
        self.assertEqual(
            availability["initial_tilt_deg"], "unavailable_placeholder"
        )
        self.assertEqual(
            {
                name
                for name, state in availability.items()
                if state != "available"
            },
            {"initial_tilt_deg"},
        )

        # No tilt threshold exists, so no rule can consume the field.
        thresholds = agent.ReleaseRiskThresholds()
        self.assertNotIn("max_initial_tilt_deg", thresholds.as_dict())
        self.assertFalse(hasattr(thresholds, "max_initial_tilt_deg"))

        # Even an arbitrarily tilted feature vector cannot be rejected for
        # its pose while every commandable orientation is axis-aligned.
        tilted = agent.ReleaseRiskFeatures(
            support_ratio=1.0,
            com_margin=1.0,
            overhang_ratio=0.0,
            drop_normalized=0.0,
            support_imbalance=0.0,
            left_right_imbalance=0.0,
            front_back_imbalance=0.0,
            initial_tilt_deg=90.0,
            initial_orientation=0,
        )
        assessment = agent.evaluate_release_risk(tilted)
        self.assertTrue(assessment.passed)
        self.assertNotIn("initial_pose", assessment.reasons)

    def test_gate_diagnostics_expose_feature_availability(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(31)
        release = agent.AABB(
            center=(0.0, 0.0, 0.5),
            size=(0.3, 0.25, 0.2),
            name="release_candidate",
        )
        diagnostics = {}

        agent.release_candidate_passes_risk_gate(
            release,
            item,
            container,
            orientation=0,
            mode="shadow",
            diagnostics=diagnostics,
            item_idx=31,
        )

        gate = diagnostics["release_risk_gate"]
        self.assertEqual(
            gate["feature_availability"]["initial_tilt_deg"],
            "unavailable_placeholder",
        )
        self.assertIn("initial_tilt_deg", gate["unavailable_features"])

    def test_release_risk_gate_modes_only_filter_before_ranking(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(23)
        release = agent.AABB(
            center=(0.0, 0.0, 0.5),
            size=(0.3, 0.25, 0.2),
            name="release_candidate",
        )
        thresholds = agent.ReleaseRiskThresholds(
            min_support_ratio=0.9,
            min_com_margin=0.5,
            max_overhang_ratio=0.1,
            max_drop_normalized=0.1,
            max_support_imbalance=0.1,
        )
        original_score = agent.Ranker.score(
            release, item, container, False
        )
        diagnostics = {}

        self.assertTrue(
            agent.release_candidate_passes_risk_gate(
                release,
                item,
                container,
                orientation=0,
                mode="off",
                thresholds=thresholds,
            )
        )
        self.assertTrue(
            agent.release_candidate_passes_risk_gate(
                release,
                item,
                container,
                orientation=0,
                mode="shadow",
                thresholds=thresholds,
                diagnostics=diagnostics,
                item_idx=23,
            )
        )
        self.assertFalse(
            agent.release_candidate_passes_risk_gate(
                release,
                item,
                container,
                orientation=0,
                mode="enforce",
                thresholds=thresholds,
            )
        )
        self.assertEqual(
            original_score,
            agent.Ranker.score(release, item, container, False),
        )
        self.assertEqual(
            diagnostics["release_risk_gate"]["would_reject"],
            1,
        )

    def test_release_generator_applies_gate_before_yielding_candidate(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        observation = {"container_list": [container]}
        item = sample_item(24)
        rejected = agent.ReleaseRiskAssessment(
            passed=False,
            reasons=("drop",),
        )

        def generated(mode):
            diagnostics = {}
            with (
                mock.patch.object(
                    agent,
                    "RELEASE_RISK_GATE_MODE",
                    mode,
                ),
                mock.patch.object(
                    agent,
                    "evaluate_release_risk",
                    return_value=rejected,
                ),
            ):
                candidates = [
                    candidate
                    for candidate in agent.CandidateGenerator.iter_attempts(
                        observation,
                        item,
                        container_idx=0,
                        orientation=0,
                        limit=1,
                        diagnostics=diagnostics,
                        item_idx=24,
                        attempt_kind="release",
                    )
                    if candidate is not None
                ]
            return candidates, diagnostics

        shadow, shadow_diagnostics = generated("shadow")
        enforced, enforced_diagnostics = generated("enforce")

        self.assertEqual(len(shadow), 1)
        self.assertEqual(enforced, [])
        self.assertGreater(
            shadow_diagnostics["release_risk_gate"]["would_reject"],
            0,
        )

        self.assertGreater(
            enforced_diagnostics["release_risk_gate"][
                "enforced_rejections"
            ],
            0,
        )

    def test_release_flow_distinguishes_static_candidates_from_all_rejected(self):
        diagnostics = {
            "by_kind": {
                "release": {
                    "attempted": 7,
                    "accepted": 4,
                    "envelope_pruned": 0,
                    "rejected": {},
                }
            },
            "release_risk_gate": {
                "mode": "enforce",
                "evaluated": 4,
                "passed": 0,
                "would_reject": 4,
                "enforced_rejections": 4,
            },
        }

        agent.finalize_release_flow_diagnostics(diagnostics)

        self.assertEqual(diagnostics["release_static_count"], 4)
        self.assertEqual(diagnostics["release_gate_pass_count"], 0)
        self.assertEqual(diagnostics["release_gate_reject_count"], 4)
        self.assertTrue(diagnostics["release_all_rejected"])

    def test_enforce_without_release_candidates_matches_off_action(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(26)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        settled = agent.AABB(
            center=(0.0, 0.0, 0.1),
            size=(0.2, 0.2, 0.2),
            name="settled_candidate",
        )

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] == "settled":
                yield settled

        actions = {}
        for mode in ("off", "enforce"):
            with (
                mock.patch.object(
                    agent.CandidateGenerator,
                    "iter_attempts",
                    side_effect=attempts,
                ),
                mock.patch.object(agent, "RELEASE_RISK_GATE_MODE", mode),
            ):
                decision = agent.PlacementCore.choose(
                    observation,
                    [(0, item)],
                )
            actions[mode] = decision.action

        self.assertEqual(
            actions["off"]["item_idx"],
            actions["enforce"]["item_idx"],
        )
        self.assertEqual(
            actions["off"]["container_idx"],
            actions["enforce"]["container_idx"],
        )
        self.assertEqual(
            actions["off"]["orientation"],
            actions["enforce"]["orientation"],
        )
        np.testing.assert_array_equal(
            actions["off"]["place_pos"],
            actions["enforce"]["place_pos"],
        )

    def test_settled_generator_never_invokes_release_gate(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        observation = {"container_list": [container]}
        item = sample_item(27, length=0.2, width=0.2, height=0.2)

        with mock.patch.object(
            agent,
            "release_candidate_passes_risk_gate",
            side_effect=AssertionError("settled candidate entered gate"),
        ):
            candidates = [
                candidate
                for candidate in agent.CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    container_idx=0,
                    orientation=0,
                    limit=1,
                    attempt_kind="settled",
                )
                if candidate is not None
            ]

        self.assertEqual(len(candidates), 1)

    def test_shadow_gate_preserves_release_candidates_and_scores(self):
        container = halfspace_container(
            lower_point=(0.0, 0.0, 0.3),
            lower_normal=(0.0, 0.0, -1.0),
        )
        observation = {"container_list": [container]}
        item = sample_item(25, length=0.4, width=0.2, height=0.2)

        def generated(mode):
            diagnostics = {}
            with mock.patch.object(
                agent,
                "RELEASE_RISK_GATE_MODE",
                mode,
            ):
                candidates = [
                    candidate
                    for candidate in agent.CandidateGenerator.iter_attempts(
                        observation,
                        item,
                        container_idx=0,
                        orientation=0,
                        limit=8,
                        diagnostics=diagnostics,
                        item_idx=25,
                        attempt_kind="release",
                    )
                    if candidate is not None
                ]
            return candidates, diagnostics

        off, _off_diagnostics = generated("off")
        shadow, shadow_diagnostics = generated("shadow")

        self.assertEqual(off, shadow)
        self.assertEqual(
            [
                agent.Ranker.score(candidate, item, container, False)
                for candidate in off
            ],
            [
                agent.Ranker.score(candidate, item, container, False)
                for candidate in shadow
            ],
        )
        self.assertGreater(
            shadow_diagnostics["release_risk_gate"]["would_reject"],
            0,
        )

        def selected_action(candidates):
            stream = [
                (0, item, 0, 0, candidate)
                for candidate in candidates
            ]
            with mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter(stream),
            ):
                return agent.PlacementCore.choose(
                    observation,
                    [(0, item)],
                ).action

        off_action = selected_action(off)
        shadow_action = selected_action(shadow)
        self.assertEqual(
            off_action["container_idx"],
            shadow_action["container_idx"],
        )
        self.assertEqual(
            off_action["orientation"],
            shadow_action["orientation"],
        )
        np.testing.assert_array_equal(
            off_action["place_pos"],
            shadow_action["place_pos"],
        )


class RankingPipelineContractTests(unittest.TestCase):
    def test_structured_noop_mode_requests_rich_evaluation_only(self):
        with mock.patch.object(
            agent, "PLACEMENT_SELECTOR_MODE", "structured_noop"
        ):
            self.assertEqual(
                agent.placement_selection_kwargs(),
                {"structured_evaluation": True},
            )
        with mock.patch.object(agent, "PLACEMENT_SELECTOR_MODE", "scalar"):
            self.assertEqual(agent.placement_selection_kwargs(), {})
        with mock.patch.object(
            agent, "PLACEMENT_SELECTOR_MODE", "structured_retained"
        ):
            self.assertEqual(
                agent.placement_selection_kwargs(),
                {"retained_evaluation": True},
            )

    def test_retained_evaluation_enriches_only_the_selected_decision(self):
        item = sample_item(8)
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        candidate = agent.AABB(
            (0.0, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "candidate",
        )
        alternate = agent.AABB(
            (0.2, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "candidate",
        )
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        yielded = [
            (0, item, 0, 0, alternate),
            (0, item, 0, 0, candidate),
        ]
        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter(yielded),
            ),
            mock.patch.object(
                agent.Ranker,
                "evaluate",
                wraps=agent.Ranker.evaluate,
            ) as rich_evaluate,
        ):
            decision = agent.PlacementCore.choose(
                observation,
                [(0, item)],
                retained_evaluation=True,
            )

        self.assertEqual(rich_evaluate.call_count, 1)
        self.assertIsNotNone(decision.evaluation)
        self.assertEqual(
            decision.evaluation.immediate.total.hex(),
            agent.Ranker.score(candidate, item, container, False).hex(),
        )
        self.assertEqual(
            decision.evaluation.provenance, "placement_core_retained"
        )

    def test_multi_axis_dominance_uses_rule_and_physical_axes_not_com(self):
        baseline = {
            "priority_cover_violations": 1,
            "soft_cover_violations": 0,
            "priority_routing_violation": 0,
            "rotation_probability": 0.4,
            "slide_probability": 0.2,
            "support_ratio": 0.5,
            "support_center_margin": 0.0,
            "predicted_com_z": 0.4,
        }
        better = dict(
            baseline,
            priority_cover_violations=0,
            rotation_probability=0.3,
            predicted_com_z=0.9,
        )
        self.assertTrue(agent.multi_axis_dominates(better, baseline))
        self.assertFalse(agent.multi_axis_dominates(baseline, better))

    def test_multi_axis_shadow_proposes_best_score_on_pareto_front(self):
        decisions = [object(), object(), object()]
        records = [
            {
                "rank": 0,
                "item_index": 10,
                "adjusted_score": 5.0,
                "priority_cover_violations": 1,
                "soft_cover_violations": 0,
                "priority_routing_violation": 0,
                "rotation_probability": 0.4,
                "slide_probability": 0.2,
                "support_ratio": 0.5,
                "support_center_margin": 0.0,
            },
            {
                "rank": 1,
                "item_index": 11,
                "adjusted_score": 4.0,
                "priority_cover_violations": 0,
                "soft_cover_violations": 0,
                "priority_cover_violations_stack": 0,
                "soft_cover_violations_stack": 0,
                "priority_routing_violation": 0,
                "rotation_probability": 0.3,
                "slide_probability": 0.2,
                "support_ratio": 0.5,
                "support_center_margin": 0.0,
            },
            {
                "rank": 2,
                "item_index": 12,
                "adjusted_score": 3.0,
                "priority_cover_violations": 0,
                "soft_cover_violations": 0,
                "priority_cover_violations_stack": 0,
                "soft_cover_violations_stack": 0,
                "priority_routing_violation": 0,
                "rotation_probability": 0.3,
                "slide_probability": 0.2,
                "support_ratio": 0.6,
                "support_center_margin": 0.0,
            },
        ]
        with mock.patch.object(
            agent,
            "multi_axis_candidate_record",
            side_effect=records,
        ):
            record = agent.multi_axis_shadow_record(
                decisions, {}, selected_decision=decisions[1]
            )

        self.assertTrue(record["baseline_dominated"])
        self.assertTrue(record["selected_dominated"])
        self.assertEqual(record["selected_rank"], 1)
        self.assertEqual(record["proposed_rank"], 2)
        self.assertTrue(record["would_change_action"])
        self.assertTrue(record["would_change_selected_action"])
        self.assertTrue(record["would_change_item"])
        self.assertEqual(record["pareto_front_size"], 1)

    def test_candidate_attribute_violations_match_incremental_rule(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            dict(
                sample_item(1, is_soft=True, is_prioritized=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        candidate = agent.AABB(
            (0.0, 0.0, 0.3), (0.3, 0.25, 0.2), "candidate"
        )
        plain = sample_item(2)
        priority, soft = agent.candidate_attribute_violations(
            plain, candidate, container
        )
        self.assertEqual((priority, soft), (1, 1))

    def test_rest_legality_matches_the_bundled_rule_on_every_combination(self):
        """The per-axis reading, checked against the simulator, not argued.

        The sentence 自分以外の属性 is read PER AXIS, and the case that
        catches a loose reading is priority-on-soft: a priority item is
        not itself soft, so resting it on a soft item IS a soft-axis
        violation. Only an item carrying every protected attribute the
        lower one has may rest on it. This enumerates all sixteen
        (lower, mover) attribute pairs and requires the agent's
        predicate to agree with calculate_attribute_placement.
        """
        import pathlib as _pathlib
        import sys as _sys

        simulator = str(
            _pathlib.Path(__file__).resolve().parents[1] / "simulator"
        )
        if simulator not in _sys.path:
            _sys.path.insert(0, simulator)
        from src.ground_handling.diagnostics import (
            calculate_attribute_placement,
        )

        def packed(index, is_soft, is_prioritized, z):
            return {
                "index": index,
                "mass": 1.0,
                "volume": 1.0,
                "pos": [0.0, 0.0, z],
                "aabb_min": [-0.2, -0.2, z - 0.1],
                "aabb_max": [0.2, 0.2, z + 0.1],
                "is_soft": is_soft,
                "is_prioritized": is_prioritized,
            }

        combinations = [(False, False), (True, False), (False, True), (True, True)]
        for lower_soft, lower_priority in combinations:
            for mover_soft, mover_priority in combinations:
                snapshot = [
                    {
                        "index": 0,
                        "offset_x": 0.0,
                        "length": 2.0,
                        "width": 1.5,
                        "height": 1.5,
                        "thickness": 0.01,
                        "buffer": 0.0,
                        "cut_x": 0.0,
                        "require_shelf": False,
                        "is_prioritized": False,
                        "volume": 4.0,
                        "packed_items": [
                            packed(0, lower_soft, lower_priority, 0.1),
                            packed(1, mover_soft, mover_priority, 0.3),
                        ],
                    }
                ]
                official = calculate_attribute_placement(snapshot)
                penalised = bool(
                    official["soft_covered_by_other"]
                    or official["priority_covered_by_other"]
                )
                mover = {
                    "is_soft": mover_soft,
                    "is_prioritized": mover_priority,
                }
                legal = agent.attribute_rest_is_legal(
                    mover, lower_soft, lower_priority
                )
                self.assertEqual(
                    legal,
                    not penalised,
                    f"lower(soft={lower_soft}, prio={lower_priority}) "
                    f"mover(soft={mover_soft}, prio={mover_priority}): "
                    f"agent says legal={legal}, simulator penalises="
                    f"{penalised}",
                )

    def test_support_surfaces_without_an_item_keeps_the_old_contract(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            dict(sample_item(1, is_soft=True), pos=[0.0, 0.0, 0.1],
                 orientation=0),
            dict(sample_item(2), pos=[0.5, 0.0, 0.1], orientation=0),
        ]

        names = [s.name for s in agent.support_surfaces(container)]

        # floor, shelves, and the plain packed item only.
        self.assertEqual(len(names), 2)

    def test_the_two_attribute_readings_agree_on_direct_contact(self):
        """Stack-awareness must be a strict widening, not a different rule.

        Both readings have to charge the resting case identically, or
        the shadow's comparison measures two unrelated things instead of
        the one structural choice under test.
        """
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            dict(
                sample_item(1, is_soft=True, is_prioritized=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        resting = agent.AABB((0.0, 0.0, 0.3), (0.3, 0.25, 0.2), "candidate")
        plain = sample_item(2)

        contact = agent.candidate_attribute_violations(
            plain, resting, container
        )
        stacked = agent.candidate_attribute_violations(
            plain, resting, container, stack_aware=True
        )

        self.assertEqual(contact, stacked)

    def test_stack_aware_charges_load_carried_through_a_gap(self):
        """The case the shipped reading misses: ordinary cargo higher up.

        A box floating a clear 40 cm over a soft item is charged by the
        stack-aware reading and not by the contact one. On recorded
        boards this is the difference between 0.19 and 2.24 violated
        soft items per episode.
        """
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        higher = agent.AABB((0.0, 0.0, 0.7), (0.3, 0.25, 0.2), "candidate")
        plain = sample_item(2)

        _, contact_soft = agent.candidate_attribute_violations(
            plain, higher, container
        )
        _, stacked_soft = agent.candidate_attribute_violations(
            plain, higher, container, stack_aware=True
        )

        self.assertEqual(contact_soft, 0)
        self.assertEqual(stacked_soft, 1)

    def test_stack_aware_ignores_items_below_and_same_attribute_above(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.9],
                orientation=0,
            )
        ]
        below = agent.AABB((0.0, 0.0, 0.2), (0.3, 0.25, 0.2), "candidate")

        _, soft_below = agent.candidate_attribute_violations(
            sample_item(2), below, container, stack_aware=True
        )
        self.assertEqual(soft_below, 0)

        container["packed_items"] = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        higher = agent.AABB((0.0, 0.0, 0.7), (0.3, 0.25, 0.2), "candidate")
        _, soft_same = agent.candidate_attribute_violations(
            sample_item(2, is_soft=True), higher, container,
            stack_aware=True,
        )
        self.assertEqual(soft_same, 0)

    def test_multi_axis_dominance_ignores_the_stack_aware_columns(self):
        """The shadow records the new reading; nothing selects on it yet.

        multi_axis_dominates fixes its own axis tuple, so adding columns
        to the record must not change any verdict. If a future arm wants
        to select on them it has to say so in a protocol, not inherit it
        silently from a logging change.
        """
        better = {
            "priority_cover_violations": 0,
            "soft_cover_violations": 0,
            "priority_cover_violations_stack": 9,
            "soft_cover_violations_stack": 9,
            "priority_routing_violation": 0,
            "rotation_probability": 0.1,
            "slide_probability": 0.1,
            "support_ratio": 0.9,
            "support_center_margin": 0.2,
        }
        worse = dict(
            better,
            soft_cover_violations=1,
            priority_cover_violations_stack=0,
            soft_cover_violations_stack=0,
        )

        self.assertTrue(agent.multi_axis_dominates(better, worse))
        self.assertFalse(agent.multi_axis_dominates(worse, better))

    def test_multi_axis_shadow_does_not_run_inside_closed_loop_selection(self):
        items = [sample_item(1), sample_item(2)]
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        observation = {
            "pool_list": items,
            "container_list": [container],
        }
        top = [
            agent.PlacementDecision(
                action={
                    "item_idx": index,
                    "container_idx": 0,
                    "place_pos": np.zeros(3, dtype=np.float32),
                    "orientation": 0,
                },
                candidate=agent.AABB(
                    (0.0, 0.0, 0.1),
                    (0.2, 0.2, 0.2),
                    "candidate",
                ),
                score=float(2 - index),
            )
            for index in range(2)
        ]
        solver = agent.Agent("")
        with (
            mock.patch.object(
                agent.PlacementCore, "top_candidates", return_value=top
            ),
            mock.patch.object(
                agent,
                "multi_axis_shadow_record",
                return_value={"would_change_action": True},
            ) as shadow_record,
            mock.patch.object(agent, "MULTI_AXIS_SELECTOR_MODE", "shadow"),
        ):
            selected = solver._closed_loop_choice(
                observation,
                items,
                list(enumerate(items)),
                deadline=time.perf_counter(),
            )

        self.assertIs(selected, top[0])
        self.assertIsNone(solver.last_multi_axis_shadow)
        shadow_record.assert_not_called()
        self.assertEqual(solver.last_top_candidates, top)

    def test_closed_loop_threads_structured_noop_into_top_candidates(self):
        item = sample_item(8)
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        decision = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.0, 0.0, 0.1),
                (0.2, 0.2, 0.2),
                "candidate",
            ),
            score=1.0,
        )
        solver = agent.Agent("")
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        with (
            mock.patch.object(
                agent, "PLACEMENT_SELECTOR_MODE", "structured_noop"
            ),
            mock.patch.object(
                agent.PlacementCore,
                "top_candidates",
                return_value=[decision],
            ) as top_candidates,
        ):
            selected = solver._closed_loop_choice(
                observation,
                [item],
                [(0, item)],
                deadline=time.perf_counter() + 10.0,
            )

        self.assertIs(selected, decision)
        self.assertTrue(
            top_candidates.call_args.kwargs["structured_evaluation"]
        )

    def test_ranker_evaluation_exposes_components_without_changing_total(self):
        candidate = agent.AABB(
            (0.1, 0.5, 0.3),
            (0.2, 0.3, 0.4),
            "settled_candidate",
        )
        item = sample_item(7, mass=5)
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )

        with mock.patch.object(
            agent.Geometry, "support_ratio", return_value=0.75
        ):
            evaluation = agent.Ranker.evaluate(
                candidate, item, container, False
            )
            scalar = agent.Ranker.score(
                candidate, item, container, False
            )

        self.assertAlmostEqual(evaluation.volume, 12.0 * 0.2 * 0.3 * 0.4)
        self.assertAlmostEqual(evaluation.support, 2.0 * 0.75)
        self.assertAlmostEqual(evaluation.depth, 0.35 * 0.5)
        self.assertAlmostEqual(evaluation.lateral, -0.12 * 0.1)
        self.assertAlmostEqual(evaluation.lift, -0.18 * 0.3 * 5.0)
        self.assertAlmostEqual(evaluation.routing, 0.0)
        self.assertAlmostEqual(evaluation.zone, 0.0)
        self.assertEqual(evaluation.total.hex(), scalar.hex())
        self.assertAlmostEqual(
            evaluation.total,
            sum(evaluation.components().values()),
        )

    def test_candidate_pipeline_separates_proposal_evaluation_and_command(self):
        candidate = agent.AABB(
            (0.2, -0.1, 0.25),
            (0.3, 0.2, 0.2),
            "settled_candidate",
        )
        item = sample_item(42)
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        proposal = agent.PlacementProposal(
            pool_index=1,
            stable_item_index=42,
            item=item,
            container_index=0,
            container=container,
            orientation=3,
            candidate=candidate,
            source="unit-test",
        )

        with mock.patch.object(
            agent.Geometry, "support_ratio", return_value=1.0
        ):
            decision = agent.evaluate_placement_proposal(
                proposal,
                has_priority_container=False,
                risk_lambda=None,
            )

        self.assertIs(decision.proposal, proposal)
        self.assertEqual(decision.command.stable_item_index, 42)
        self.assertEqual(decision.command.mode, "settled")
        self.assertEqual(decision.evaluation.provenance, "unit-test")
        self.assertAlmostEqual(
            decision.score, decision.evaluation.adjusted_score
        )
        self.assertEqual(decision.evaluation.risk.total_penalty, 0.0)
        self.assertEqual(decision.action["item_idx"], 1)
        self.assertEqual(decision.action["orientation"], 3)
        np.testing.assert_allclose(
            decision.action["place_pos"], candidate.center
        )

        record = agent.placement_evaluation_record(decision)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["stable_item_index"], 42)
        self.assertEqual(record["command_mode"], "settled")
        np.testing.assert_array_equal(
            agent.action_for_execution(decision)["place_pos"],
            decision.action["place_pos"],
        )

    def test_placement_core_accepts_a_selector_without_regenerating_candidates(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(9)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        first = agent.AABB(
            (0.1, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "settled_candidate",
        )
        second = agent.AABB(
            (0.2, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "settled_candidate",
        )

        class ChooseLast:
            def __init__(self):
                self.seen = []

            def observe(self, decision):
                self.seen.append(decision)
                return True

            def select(self):
                return self.seen[-1]

        selector = ChooseLast()
        stream = iter(
            [
                (0, item, 0, 0, first),
                (0, item, 0, 0, second),
            ]
        )
        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=stream,
            ),
            mock.patch.object(
                agent.Ranker,
                "evaluate",
                side_effect=[10.0, 1.0],
            ),
        ):
            selected = agent.PlacementCore.choose(
                observation,
                [(0, item)],
                selector=selector,
            )

        self.assertEqual(len(selector.seen), 2)
        self.assertIsNotNone(selector.seen[0].evaluation)
        self.assertIs(selected.candidate, second)
        self.assertEqual(selected.score, 1.0)

    def test_default_selector_keeps_the_allocation_light_scalar_path(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(3)
        candidate = agent.AABB(
            (0.1, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "settled_candidate",
        )
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter([(0, item, 0, 0, candidate)]),
            ),
            mock.patch.object(agent.Ranker, "score", return_value=2.0),
            mock.patch.object(
                agent.Ranker,
                "evaluate",
                side_effect=AssertionError("rich path must be opt-in"),
            ),
        ):
            selected = agent.PlacementCore.choose(
                observation,
                [(0, item)],
            )

        self.assertEqual(selected.score, 2.0)
        self.assertIsNone(selected.proposal)
        self.assertIsNone(selected.command)
        self.assertIsNone(selected.evaluation)

    def test_default_top_k_keeps_the_allocation_light_scalar_path(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(4)
        candidate = agent.AABB(
            (0.1, 0.0, 0.1),
            (0.2, 0.2, 0.2),
            "settled_candidate",
        )
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter([(0, item, 0, 0, candidate)]),
            ),
            mock.patch.object(agent.Ranker, "score", return_value=3.0),
            mock.patch.object(
                agent.Ranker,
                "evaluate",
                side_effect=AssertionError("rich path must be opt-in"),
            ),
        ):
            selected = agent.PlacementCore.top_candidates(
                observation,
                [(0, item)],
                k=1,
            )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].score, 3.0)
        self.assertIsNone(selected[0].evaluation)


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

    def test_class_aware_cap_includes_each_present_item_class(self):
        pool = [sample_item(index) for index in range(12)]
        pool.append(sample_item(12, is_soft=True))
        pool.append(sample_item(13, is_prioritized=True))

        selected = agent.capped_online_items(
            pool,
            limit=10,
            mode="class_aware",
        )
        selected_indices = [int(item["index"]) for _, item in selected]

        self.assertEqual(selected_indices[:3], [0, 12, 13])
        self.assertEqual(len(selected_indices), 10)
        self.assertEqual(
            {agent.item_class_name(item) for _, item in selected},
            {"normal", "soft", "priority"},
        )

    def test_legacy_cap_preserves_the_original_prefix(self):
        pool = [sample_item(index) for index in range(12)]
        pool.append(sample_item(12, is_soft=True))
        pool.append(sample_item(13, is_prioritized=True))

        selected = agent.capped_online_items(
            pool,
            limit=10,
            mode="legacy",
        )

        self.assertEqual(
            [int(item["index"]) for _, item in selected],
            list(range(10)),
        )

    def test_late_item_cap_activates_only_after_minimum_placed(self):
        before = {"container_list": [{"packed_items": [1, 2, 3, 4, 5]}]}
        after = {"container_list": [{"packed_items": [1, 2, 3, 4, 5, 6]}]}
        with (
            mock.patch.object(agent, "MAX_POOL_ITEMS_EVALUATED", 10),
            mock.patch.object(agent, "LATE_POOL_ITEMS_EVALUATED", 20),
            mock.patch.object(agent, "LATE_POOL_MIN_PLACED", 6),
        ):
            self.assertEqual(agent.effective_online_item_cap(before), 10)
            self.assertEqual(agent.effective_online_item_cap(after), 20)

    def test_late_item_cap_can_be_limited_to_narrow_visible_pools(self):
        narrow = {"container_list": [{"packed_items": [1] * 6}],
                  "pool_list": [object()] * 15}
        wide = {"container_list": [{"packed_items": [1] * 6}],
                "pool_list": [object()] * 20}
        with (
            mock.patch.object(agent, "MAX_POOL_ITEMS_EVALUATED", 10),
            mock.patch.object(agent, "LATE_POOL_ITEMS_EVALUATED", 16),
            mock.patch.object(agent, "LATE_POOL_MIN_PLACED", 6),
            mock.patch.object(agent, "LATE_POOL_MAX_VISIBLE", 16),
        ):
            self.assertEqual(agent.effective_online_item_cap(narrow), 16)
            self.assertEqual(agent.effective_online_item_cap(wide), 10)

    def test_class_aware_units_start_each_item_before_remaining_units(self):
        observation = {
            "pool_list": [sample_item(index) for index in range(3)],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        indexed_items = list(enumerate(observation["pool_list"]))

        units = agent.prioritized_search_units(
            observation,
            indexed_items,
            class_aware_first_pass=True,
        )

        self.assertEqual(
            [unit[5]["index"] for unit in units[:3]],
            [0, 1, 2],
        )

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

    def test_true_envelope_follows_asymmetric_container_walls(self):
        # The AKE/AKN-derived containers have y planes at [-W/2, +W/2 - t],
        # not at +/-(W/2 - t). The box formula subtracts a thickness from
        # both sides, so the low-y side is one thickness too tight for every
        # item and both generators -- the band that held sixteen physically
        # safe placements where an exhaustive run found none.
        width, length, thickness = 1.52, 2.0, 0.05
        container = {
            "index": 0,
            "length": length,
            "width": width,
            "height": 1.61,
            "thickness": thickness,
            "packed_items": [],
            "points": [
                [length / 2.0 - thickness, 0.0, 0.8],
                [-length / 2.0 + thickness, 0.0, 0.8],
                [0.0, -width / 2.0, 0.8],
                [0.0, width / 2.0 - thickness, 0.8],
            ],
            "n_vecs": [
                [1.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0],
                [0.0, -1.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
        }
        dims = (0.65, 0.45, 0.25)

        with mock.patch.object(agent, "ANCHOR_TRUE_ENVELOPE", False):
            box = agent.rectangular_container_anchor_bounds(dims, container)
        with mock.patch.object(agent, "ANCHOR_TRUE_ENVELOPE", True):
            true = agent.rectangular_container_anchor_bounds(dims, container)

        # x is symmetric in this geometry, so the two agree there.
        self.assertAlmostEqual(box[0], true[0], places=9)
        self.assertAlmostEqual(box[1], true[1], places=9)
        # y is not: the low side gains exactly one thickness, the high side
        # is unchanged. Anything else means the bound stopped tracking the
        # container.
        self.assertAlmostEqual(box[2] - true[2], thickness, places=9)
        self.assertAlmostEqual(box[3], true[3], places=9)

    def test_true_envelope_falls_back_without_a_half_space_model(self):
        # A container dict with no points/n_vecs is not an error: the offline
        # dry run and several tests build containers by hand. Widening a
        # bound from a model that is not there would be worse than the box.
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container.pop("points", None)
        container.pop("n_vecs", None)
        dims = (0.4, 0.3, 0.2)

        with mock.patch.object(agent, "ANCHOR_TRUE_ENVELOPE", True):
            bounds = agent.rectangular_container_anchor_bounds(
                dims, container
            )
        with mock.patch.object(agent, "ANCHOR_TRUE_ENVELOPE", False):
            box = agent.rectangular_container_anchor_bounds(dims, container)

        self.assertEqual(bounds, box)

    def test_true_envelope_is_on_by_default(self):
        # Shipped 2026-08-02. Pinned because the whole point is that the
        # envelope and the containment test agree about the container; a
        # silent revert would put them back out of step without any test
        # noticing, which is exactly how the band went unseen for so long.
        self.assertTrue(agent.ANCHOR_TRUE_ENVELOPE)

    def test_tilt_margin_retreats_by_sin_theta_times_item_height(self):
        # The fill evaluator forfeits an item whose settled top corner
        # crosses a boundary plane, and the lean scales with item height,
        # so the margin must too: same angle, taller item, bigger retreat.
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container.pop("points", None)
        container.pop("n_vecs", None)
        short = (0.45, 0.30, 0.20)
        tall = (0.25, 0.45, 0.65)

        for dims in (short, tall):
            with mock.patch.object(agent, "ANCHOR_TILT_MARGIN_DEG", 0.0):
                base = agent.rectangular_container_anchor_bounds(
                    dims, container
                )
            with mock.patch.object(agent, "ANCHOR_TILT_MARGIN_DEG", 4.0):
                shrunk = agent.rectangular_container_anchor_bounds(
                    dims, container
                )
            margin = math.sin(math.radians(4.0)) * dims[2]
            self.assertAlmostEqual(shrunk[0] - base[0], margin, places=9)
            self.assertAlmostEqual(base[1] - shrunk[1], margin, places=9)
            self.assertAlmostEqual(shrunk[2] - base[2], margin, places=9)
            self.assertAlmostEqual(base[3] - shrunk[3], margin, places=9)

    def test_tilt_margin_is_off_by_default(self):
        self.assertEqual(agent.ANCHOR_TILT_MARGIN_DEG, 0.0)

    def test_stride_fallback_covers_the_whole_grid_at_every_level(self):
        # The point of the ladder is coverage, not depth: a level cut short
        # must still have looked everywhere at its resolution. A dense scan
        # truncated by the deadline explores one corner instead, which is
        # what makes the primary space's blindness fatal.
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(3, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        seen_strides = []
        seen_kinds = []

        def attempts(*_args, **kwargs):
            seen_strides.append(kwargs["stride"])
            seen_kinds.append(kwargs["attempt_kind"])
            yield agent.AABB(
                (0.1, 0.2, 0.14), (0.2, 0.2, 0.2), "candidate"
            )

        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_cartesian_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(
                agent, "ANCHOR_FALLBACK_STRIDES", (8, 2)
            ),
        ):
            diagnostics = {}
            produced = list(
                agent.iter_stride_fallback_candidates(
                    observation,
                    [(0, item)],
                    diagnostics=diagnostics,
                )
            )

        self.assertTrue(produced)
        self.assertEqual(sorted(set(seen_strides)), [2, 8])
        # Coarsest level first, and every unit visited before refining.
        self.assertEqual(
            seen_strides,
            [8] * (len(seen_strides) // 2) + [2] * (len(seen_strides) // 2),
        )
        # Release units precede settled ones within each level: the settled
        # cartesian space is an order of magnitude more expensive per
        # candidate, so a settled-first sweep spends the whole fallback
        # budget without accepting anything.
        first_level = seen_kinds[: len(seen_kinds) // 2]
        self.assertEqual(
            first_level,
            sorted(first_level, key=lambda kind: kind != "release"),
        )
        self.assertEqual(first_level[0], "release")
        fallback = diagnostics["search"]["anchor_fallback"]
        self.assertEqual(fallback["levels_started"], 2)
        self.assertEqual(fallback["levels_completed"], 2)
        self.assertEqual(fallback["accepted"], len(produced))
        self.assertIsNotNone(fallback["first_accepted_seconds"])

    def test_stride_fallback_stops_at_the_deadline(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        item = sample_item(3, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }

        def attempts(*_args, **_kwargs):
            yield None

        with mock.patch.object(
            agent.CandidateGenerator,
            "iter_cartesian_attempts",
            side_effect=attempts,
        ):
            diagnostics = {}
            produced = list(
                agent.iter_stride_fallback_candidates(
                    observation,
                    [(0, item)],
                    deadline=time.perf_counter() - 1.0,
                    diagnostics=diagnostics,
                )
            )

        self.assertEqual(produced, [])
        self.assertTrue(
            diagnostics["search"]["anchor_fallback"]["deadline_reached"]
        )

    def test_anchor_fallback_is_off_by_default(self):
        # Every earlier fallback design in this repository looked good on
        # static replay and lost on physics, so this one ships off until an
        # ablation says otherwise.
        self.assertFalse(agent.ANCHOR_FALLBACK_ENABLED)

    def test_candidate_audit_records_per_unit_progress(self):
        # Accepted-candidate lists cannot separate a unit the search never
        # reached from one it visited without spending enough attempts, and
        # those two diagnoses call for opposite fixes: reorder the units, or
        # keep an anytime incumbent. The per-unit rows carry that split.
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

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] == "settled":
                yield settled

        diagnostics = {}
        with (
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent, "CANDIDATE_AUDIT_ENABLED", True),
        ):
            list(
                agent.iter_prioritized_candidates(
                    observation,
                    [(0, item)],
                    diagnostics=diagnostics,
                )
            )

        units = diagnostics["candidate_audit"][0]["units"]
        self.assertEqual(
            len(units), diagnostics["search"]["units_total"]
        )
        self.assertEqual(
            [entry["unit_rank"] for entry in units],
            list(range(len(units))),
        )
        for entry in units:
            self.assertIn(entry["attempt_kind"], {"settled", "release"})
            self.assertEqual(entry["item_index"], 7)
        started = [entry for entry in units if entry["started"]]
        self.assertTrue(started)
        self.assertTrue(
            all(
                entry["first_seen_seconds"] is not None
                for entry in started
            )
        )
        # Every unit here runs to exhaustion, so accepted counts must agree
        # with the accepted list rather than being tracked independently.
        self.assertTrue(all(entry["exhausted"] for entry in started))
        self.assertEqual(
            sum(entry["accepted"] for entry in units),
            len(diagnostics["candidate_audit"][0]["accepted_settled"])
            + len(diagnostics["candidate_audit"][0]["accepted_release"]),
        )

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
            with (
                mock.patch.dict(
                    os.environ,
                    {"NEDO_POLICY_TRACE_PATH": str(trace_path)},
                ),
                # This test pins the exact trace shape; the shipped
                # guard_quiet default adds physics_probe_guard events,
                # exercised by its own tests and the ablation arms.
                mock.patch.object(agent, "PHYSICS_PROBE_MODE", "off"),
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

    def test_unsafe_protocol_fallback_is_included_in_policy_trace(self):
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
        self.assertEqual(
            events[1]["action_source"],
            "unsafe_protocol_fallback",
        )
        self.assertEqual(events[1]["internal_outcome"], "no_safe_action")
        self.assertTrue(events[1]["no_safe_action"])
        self.assertEqual(events[1]["protocol_fallback"], "fixed")
        self.assertEqual(
            events[1]["protocol_fallback_kind"],
            "fixed_coordinate",
        )
        self.assertEqual(events[1]["selected_item_index"], 9)
        lifecycle = {
            record["item_index"]: record
            for record in events[1]["item_lifecycle"]
        }
        self.assertIsNone(lifecycle[9]["selected_step"])
        self.assertEqual(
            lifecycle[9]["starvation_observation"],
            "unsafe_protocol_fallback_target",
        )
        self.assertEqual(
            solver.last_action_source,
            "unsafe_protocol_fallback",
        )
        self.assertEqual(
            solver.last_candidate_kind,
            "unsafe_protocol_fallback",
        )

    def test_policy_trace_records_item_selection_lifecycle_stages(self):
        pool = [sample_item(index) for index in range(11)]
        pool.append(sample_item(11, is_prioritized=True))
        observation = {
            "pool_list": pool,
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        candidate = agent.AABB(
            center=np.array([0.0, 0.0, 0.1]),
            size=np.array([0.3, 0.25, 0.2]),
            name="settled_candidate",
        )
        decisions = [
            agent.PlacementDecision(
                action={
                    "item_idx": pool_index,
                    "container_idx": 0,
                    "place_pos": np.array([0.0, 0.0, 0.1]),
                    "orientation": 0,
                },
                candidate=candidate,
                score=float(10 - pool_index),
            )
            for pool_index in (0, 1)
        ]

        def top_candidates(
            _observation,
            _indexed_items,
            _k,
            deadline=None,
            diagnostics=None,
            risk_lambda=None,
        ):
            diagnostics["search"] = {
                "units_total": 20,
                "units_started": 20,
                "units_completed": 20,
                "rounds_started": 1,
                "deadline_reached": False,
                "incumbent_updates": 2,
                "item_indices_started": list(range(10)),
                "item_indices_with_candidates": [0, 1, 2],
            }
            return decisions

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
                    side_effect=top_candidates,
                ),
                mock.patch.object(
                    agent,
                    "evaluate_visible_pool_feasibility",
                    return_value=agent.VisiblePoolFeasibility(
                        feasible_items=2,
                        evaluated_items=2,
                        best_score=1.0,
                    ),
                ),
                # Trace-shape test: the shipped guard_quiet default would
                # attach the observed-pool collector and add its own
                # events; the guard has its own tests.
                mock.patch.object(agent, "PHYSICS_PROBE_MODE", "off"),
            ):
                solver = agent.Agent("")
                solver.get_init_states(
                    {
                        "optimize": False,
                        "lookahead_k": len(pool),
                        "container_list": observation["container_list"],
                    }
                )
                solver.policy(observation)

            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        decision_event = events[1]
        stages = decision_event["selection_stages"]
        self.assertEqual(stages["visible_item_indices"], list(range(12)))
        self.assertEqual(
            stages["item_cap_item_indices"],
            [0, 11, *range(1, 9)],
        )
        self.assertEqual(stages["search_started_item_indices"], list(range(10)))
        self.assertEqual(
            stages["candidate_generated_item_indices"],
            [0, 1, 2],
        )
        self.assertEqual(stages["candidate_topk_item_indices"], [0, 1])
        self.assertEqual(stages["future_probe_item_indices"], [0, 11, 1])

        lifecycle = {
            record["item_index"]: record
            for record in decision_event["item_lifecycle"]
        }
        self.assertEqual(lifecycle[0]["item_class"], "normal")
        self.assertEqual(lifecycle[0]["selected_step"], 0)
        self.assertEqual(lifecycle[0]["starvation_observation"], "selected")
        self.assertEqual(lifecycle[2]["candidate_generated_steps"], [0])
        self.assertEqual(
            lifecycle[2]["starvation_observation"],
            "generated_but_low_rank",
        )
        self.assertEqual(lifecycle[11]["item_class"], "priority")
        self.assertEqual(lifecycle[11]["search_included_steps"], [0])
        self.assertEqual(
            lifecycle[11]["starvation_observation"],
            "search_not_started",
        )
        coverage = decision_event["coverage"]
        self.assertEqual(coverage["overall"]["visible"], 12)
        self.assertEqual(coverage["overall"]["included"], 10)
        self.assertEqual(coverage["overall"]["search_started"], 9)
        self.assertEqual(coverage["overall"]["candidate_generated"], 3)
        self.assertAlmostEqual(
            coverage["overall"]["included_over_visible"],
            10 / 12,
        )
        self.assertAlmostEqual(
            coverage["overall"]["started_over_included"],
            9 / 10,
        )
        self.assertAlmostEqual(
            coverage["overall"]["generated_over_started"],
            3 / 9,
        )
        self.assertEqual(
            coverage["by_class"]["priority"],
            {
                "visible": 1,
                "included": 1,
                "search_started": 0,
                "candidate_generated": 0,
                "included_over_visible": 1.0,
                "started_over_included": 0.0,
                "generated_over_started": None,
            },
        )

    def test_trace_disabled_does_not_collect_item_lifecycle(self):
        item = sample_item(0)
        observation = {
            "pool_list": [item],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        decision = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.array([0.0, 0.0, 0.1]),
                "orientation": 0,
            },
            candidate=agent.AABB(
                center=np.array([0.0, 0.0, 0.1]),
                size=np.array([0.3, 0.25, 0.2]),
                name="settled_candidate",
            ),
            score=1.0,
        )
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                agent.Agent,
                "_closed_loop_choice",
                return_value=decision,
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
            solver.policy(observation)

        self.assertEqual(solver._item_lifecycle, {})
        self.assertNotIn(
            "_record_item_lifecycle",
            solver.last_candidate_diagnostics,
        )

    def test_item_lifecycle_accumulates_and_resets_per_episode(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )

        def top_candidates(
            _observation,
            indexed_items,
            _k,
            deadline=None,
            diagnostics=None,
            risk_lambda=None,
        ):
            pool_index, item = indexed_items[0]
            item_indices = [
                int(indexed_item["index"])
                for _, indexed_item in indexed_items
            ]
            diagnostics["search"] = {
                "units_total": len(indexed_items),
                "units_started": len(indexed_items),
                "units_completed": len(indexed_items),
                "rounds_started": 1,
                "deadline_reached": False,
                "incumbent_updates": 1,
                "item_indices_started": item_indices,
                "item_indices_with_candidates": item_indices,
            }
            return [
                agent.PlacementDecision(
                    action={
                        "item_idx": pool_index,
                        "container_idx": 0,
                        "place_pos": np.array([0.0, 0.0, 0.1]),
                        "orientation": 0,
                    },
                    candidate=agent.AABB(
                        center=np.array([0.0, 0.0, 0.1]),
                        size=np.array([0.3, 0.25, 0.2]),
                        name="settled_candidate",
                    ),
                    score=1.0,
                )
            ]

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
                    side_effect=top_candidates,
                ),
                # Trace-shape test: the shipped guard_quiet default would
                # attach the observed-pool collector and add its own
                # events; the guard has its own tests.
                mock.patch.object(agent, "PHYSICS_PROBE_MODE", "off"),
            ):
                solver = agent.Agent("")
                init_states = {
                    "optimize": False,
                    "lookahead_k": 2,
                    "container_list": [container],
                }
                solver.get_init_states(init_states)
                solver.policy(
                    {
                        "pool_list": [sample_item(0), sample_item(1)],
                        "container_list": [container],
                    }
                )
                solver.policy(
                    {
                        "pool_list": [sample_item(1)],
                        "container_list": [container],
                    }
                )
                events = [
                    json.loads(line)
                    for line in trace_path.read_text(
                        encoding="utf-8"
                    ).splitlines()
                ]
                second_lifecycle = {
                    record["item_index"]: record
                    for record in events[-1]["item_lifecycle"]
                }
                self.assertEqual(second_lifecycle[0]["visible_steps"], [0])
                self.assertEqual(second_lifecycle[0]["selected_step"], 0)
                self.assertEqual(
                    second_lifecycle[1]["visible_steps"], [0, 1]
                )
                self.assertEqual(second_lifecycle[1]["selected_step"], 1)

                solver.get_init_states(init_states)

        self.assertEqual(solver._item_lifecycle, {})
        self.assertEqual(solver._policy_step, 0)


class StrideSamplingTests(unittest.TestCase):
    def _observation(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        item = sample_item(0, length=0.3, width=0.25, height=0.2)
        return {"pool_list": [item], "container_list": [container]}, item

    def _accepted(self, observation, item, kind, stride=1, offset=0):
        results = []
        for candidate in agent.CandidateGenerator.iter_cartesian_attempts(
            observation,
            item,
            0,
            0,
            limit=10_000,
            attempt_kind=kind,
            stride=stride,
            stride_offset=offset,
        ):
            if candidate is not None:
                results.append(
                    tuple(round(v, 6) for v in candidate.center)
                )
        return results

    def test_stride_one_is_unchanged_default(self):
        observation, item = self._observation()
        self.assertEqual(
            self._accepted(observation, item, "settled"),
            self._accepted(observation, item, "settled", stride=1),
        )

    def test_stride_phases_partition_the_accepted_set(self):
        observation, item = self._observation()
        for kind in ("settled", "release"):
            full = self._accepted(observation, item, kind)
            phases = [
                self._accepted(observation, item, kind, stride=3, offset=k)
                for k in range(3)
            ]
            combined = sorted(sum(phases, []))
            self.assertEqual(combined, sorted(full))
            for phase in phases:
                self.assertLess(len(phase), len(full))


class SupportPlaneStrideSamplingTests(unittest.TestCase):
    """
    ``support_plane`` is the default generator mode, so a strided rollout
    measurement only reaches a different anchor set if the stride is honoured
    here.  Striding the Cartesian generator alone changes nothing on the
    shipped path.
    """

    def _observation(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        item = sample_item(0, length=0.3, width=0.25, height=0.2)
        return {"pool_list": [item], "container_list": [container]}, item

    def _accepted(self, observation, item, kind, stride=1, offset=0):
        results = []
        iterator = agent.CandidateGenerator.iter_support_plane_attempts(
            observation,
            item,
            0,
            0,
            limit=10_000,
            attempt_kind=kind,
            stride=stride,
            stride_offset=offset,
        )
        for candidate in iterator:
            if candidate is not None:
                results.append(
                    tuple(round(v, 6) for v in candidate.center)
                )
        return results

    def test_stride_one_is_unchanged_default(self):
        observation, item = self._observation()
        self.assertEqual(
            self._accepted(observation, item, "settled"),
            self._accepted(observation, item, "settled", stride=1),
        )

    def test_stride_phases_partition_the_accepted_set(self):
        observation, item = self._observation()
        for kind in ("settled", "release"):
            full = self._accepted(observation, item, kind)
            self.assertTrue(full, f"no {kind} candidates to partition")
            phases = [
                self._accepted(observation, item, kind, stride=3, offset=k)
                for k in range(3)
            ]
            self.assertEqual(sorted(sum(phases, [])), sorted(full))
            for phase in phases:
                self.assertLess(len(phase), len(full))

    def test_stride_reaches_deeper_anchors_at_a_fixed_budget(self):
        """A strided skip must be free, not a consumed round slot."""
        observation, item = self._observation()

        def prefix(stride):
            seen = []
            iterator = agent.CandidateGenerator.iter_support_plane_attempts(
                observation,
                item,
                0,
                0,
                limit=10_000,
                attempt_kind="settled",
                stride=stride,
            )
            for attempt, candidate in enumerate(iterator):
                if attempt >= 4:
                    break
                if candidate is not None:
                    seen.append(tuple(round(v, 6) for v in candidate.center))
            return seen

        strided = prefix(4)
        baseline = prefix(1)
        self.assertTrue(strided)
        # Same number of yielded attempts, but the strided arm must have
        # travelled past the anchors the unstrided prefix stopped at.
        self.assertTrue(
            set(strided) - set(baseline),
            "stride did not expose any anchor outside the plain prefix",
        )

    def test_iter_attempts_forwards_stride_to_the_default_mode(self):
        observation, item = self._observation()

        def accepted(stride):
            return [
                tuple(round(v, 6) for v in candidate.center)
                for candidate in agent.CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    0,
                    0,
                    limit=10_000,
                    attempt_kind="settled",
                    stride=stride,
                )
                if candidate is not None
            ]

        full = accepted(1)
        strided = accepted(3)
        self.assertTrue(full)
        self.assertLess(len(strided), len(full))
        self.assertTrue(set(strided) <= set(full))


class InterleavedScanOrderTests(unittest.TestCase):
    """
    Interleave is a permutation; stride is a subsample. Confusing the two
    would silently drop anchors from a search that has time to reach them.
    """

    def test_interleave_one_is_the_shipped_order(self):
        positions = list(range(10))

        self.assertEqual(
            agent.interleaved_scan_order(positions, 1), positions
        )

    def test_interleave_keeps_every_anchor_exactly_once(self):
        positions = list(range(37))

        for interleave in (2, 3, 4, 8):
            reordered = agent.interleaved_scan_order(positions, interleave)
            self.assertEqual(
                sorted(reordered),
                positions,
                f"interleave {interleave} did not permute",
            )

    def test_the_prefix_spans_the_whole_list(self):
        positions = list(range(64))

        prefix = agent.interleaved_scan_order(positions, 8)[:8]

        self.assertEqual(prefix, [0, 8, 16, 24, 32, 40, 48, 56])

    def test_a_list_no_longer_than_the_interleave_is_untouched(self):
        positions = list(range(3))

        self.assertEqual(
            agent.interleaved_scan_order(positions, 8), positions
        )


class LiveInterleaveTests(unittest.TestCase):
    def _observation(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        item = sample_item(0, length=0.3, width=0.25, height=0.2)
        return {"pool_list": [item], "container_list": [container]}, item

    def _accepted(self, observation, item, interleave):
        return [
            tuple(round(v, 6) for v in candidate.center)
            for candidate in agent.CandidateGenerator.iter_attempts(
                observation,
                item,
                0,
                0,
                limit=10_000,
                attempt_kind="settled",
                interleave=interleave,
            )
            if candidate is not None
        ]

    def test_an_exhausted_search_sees_the_same_candidate_set(self):
        """The live search often exhausts a unit; nothing may be lost."""
        observation, item = self._observation()

        shipped = self._accepted(observation, item, 1)
        interleaved = self._accepted(observation, item, 4)

        self.assertTrue(shipped)
        self.assertEqual(sorted(interleaved), sorted(shipped))

    def test_a_truncated_search_reaches_different_anchors(self):
        observation, item = self._observation()

        shipped = self._accepted(observation, item, 1)[:3]
        interleaved = self._accepted(observation, item, 4)[:3]

        self.assertNotEqual(interleaved, shipped)

    def test_cartesian_mode_refuses_an_interleave_it_cannot_honour(self):
        observation, item = self._observation()

        with self.assertRaises(ValueError) as caught:
            list(
                agent.CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    0,
                    0,
                    generator_mode="cartesian",
                    interleave=4,
                )
            )

        self.assertIn("support_plane", str(caught.exception))

    def test_cartesian_mode_still_runs_at_the_default_interleave(self):
        observation, item = self._observation()

        accepted = [
            candidate
            for candidate in agent.CandidateGenerator.iter_attempts(
                observation,
                item,
                0,
                0,
                limit=50,
                attempt_kind="settled",
                generator_mode="cartesian",
            )
            if candidate is not None
        ]

        self.assertTrue(accepted)

    def test_the_shipped_default_is_the_shipped_order(self):
        self.assertEqual(agent.LIVE_SEARCH_INTERLEAVE, 1)


class FixedWorkModeTests(unittest.TestCase):
    """
    The online search is bounded by the wall clock, which makes the policy a
    function of machine load as well as of the state. The work bound is a
    measurement control, not a shipping change: it must be off by default and
    must not alter the shipped call shape when off.

    Two implementations of this idea were developed in parallel on separate
    branches. POLICY_ATTEMPT_BUDGET won because it also records the work the
    SHIPPED deadline path consumes, which is what a budget has to be
    calibrated from; ONLINE_FIXED_WORK_ATTEMPTS was removed rather than left
    beside it as a second name for the same control.
    """

    def test_shipped_default_is_wall_clock(self):
        self.assertEqual(agent.POLICY_ATTEMPT_BUDGET, 0)

    def test_an_explicit_budget_beats_the_constant(self):
        """
        The constant bounds the online path without threading; the parameter
        lets an offline probe ask for a specific amount of work on a captured
        state. Explicit has to win, or the probe silently measures something
        else.
        """
        self.assertEqual(agent.effective_attempt_budget(4096), 4096)

    def test_no_budget_and_no_constant_means_no_bound(self):
        self.assertIsNone(agent.effective_attempt_budget(None))

    def test_choose_stops_on_the_attempt_budget(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        items = [sample_item(i) for i in range(3)]
        observation = {"pool_list": items, "container_list": [container]}
        diagnostics = {}

        agent.PlacementCore.choose(
            observation,
            list(enumerate(items)),
            diagnostics=diagnostics,
            attempt_budget=32,
        )

        self.assertLessEqual(
            diagnostics["search"].get("attempts_consumed", 0), 32
        )

    def test_an_unset_budget_leaves_the_search_unbounded_by_work(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        items = [sample_item(0)]
        observation = {"pool_list": items, "container_list": [container]}
        diagnostics = {}

        agent.PlacementCore.choose(
            observation, list(enumerate(items)), diagnostics=diagnostics
        )

        # Recorded unconditionally by design: the SHIPPED deadline path is
        # the one whose irreproducibility is the problem, so it has to
        # report the work it consumed or the budget cannot be calibrated
        # from it. What "unbounded" means here is that nothing stopped the
        # scan early, not that nothing was counted.
        self.assertIn("attempts_consumed", diagnostics["search"])
        self.assertEqual(
            diagnostics["search"]["units_started"],
            diagnostics["search"]["units_completed"],
        )


class RolloutStrideThreadingTests(unittest.TestCase):
    """The stride has to survive both layers above the generator."""

    def _observation(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        items = [
            sample_item(index, length=0.3, width=0.25, height=0.2)
            for index in range(3)
        ]
        return {"pool_list": items, "container_list": [container]}, items

    def test_prioritized_stream_spends_its_budget_on_wider_anchors(self):
        observation, items = self._observation()
        indexed_items = list(enumerate(items))

        def centers(stride):
            found = []
            stream = agent.iter_prioritized_candidates(
                observation,
                indexed_items,
                attempt_budget=48,
                stride=stride,
            )
            for _idx, _item, _c_idx, _orient, candidate in stream:
                found.append(tuple(round(v, 6) for v in candidate.center))
            return found

        baseline = centers(1)
        strided = centers(4)
        self.assertTrue(baseline)
        self.assertNotEqual(baseline, strided)

    def test_bounded_rollout_decision_accepts_a_stride(self):
        observation, items = self._observation()
        indexed_items = list(enumerate(items))
        decision, attempts, accepted = agent.bounded_rollout_decision(
            observation,
            indexed_items,
            48,
            stride=4,
        )
        self.assertIsNotNone(decision)
        self.assertGreater(accepted, 0)
        self.assertLessEqual(attempts, 48)

    def test_rollout_evaluation_records_the_stride_it_used(self):
        observation, items = self._observation()
        indexed_items = list(enumerate(items))
        decision, _attempts, _accepted = agent.bounded_rollout_decision(
            observation, indexed_items, 64
        )
        self.assertIsNotNone(decision)
        record, _proposal = agent.visible_pool_rollout_evaluation(
            observation,
            indexed_items,
            [decision],
            decision,
            stride=4,
        )
        self.assertEqual(record["stride"], 4)


class ShadowRerankTests(unittest.TestCase):
    def _release_scenario(self):
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
        risky = agent.AABB((0.0, 0.0, 0.2), (0.2, 0.2, 0.2),
                           "release_candidate")
        safe = agent.AABB((0.3, 0.0, 0.2), (0.2, 0.2, 0.2),
                          "release_candidate")

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] == "release":
                yield risky
                yield safe

        def score(candidate, *_args):
            return 10.0 if candidate.center[0] == 0.0 else 8.0

        def probability(features):
            return 0.9 if features.center[0] == 0.0 else 0.05

        patches = (
            mock.patch.object(
                agent.CandidateGenerator, "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent.Ranker, "score", side_effect=score),
            mock.patch.object(
                agent, "release_risk_features",
                side_effect=lambda candidate, *_a, **_k: candidate,
            ),
            mock.patch.object(
                agent, "release_rotation_risk_probability",
                side_effect=probability,
            ),
            # These scenarios mock the STATIC probability and exercise
            # baseline-vs-shadow behaviour, so pin the pre-switch
            # defaults explicitly.
            mock.patch.object(agent, "RELEASE_RISK_P_MODEL", "static"),
            mock.patch.object(agent, "RELEASE_RISK_LIVE_RERANK", False),
            mock.patch.object(agent, "RELEASE_RISK_SLIDE_LAMBDA", 0.0),
        )
        return observation, risky, safe, patches

    def test_risk_probability_decreases_with_support_ratio(self):
        base = {
            "support_ratio": 0.2,
            "com_margin": 0.0,
            "drop_normalized": 0.15,
            "support_imbalance": 0.2,
            "left_right_imbalance": 0.0,
            "front_back_imbalance": 0.0,
        }
        low_support = agent.release_rotation_risk_probability(base)
        high_support = agent.release_rotation_risk_probability(
            {**base, "support_ratio": 0.9}
        )
        self.assertGreater(low_support, high_support)
        self.assertTrue(0.0 <= high_support <= 1.0)

    def test_shadow_rerank_records_change_but_keeps_the_action(self):
        observation, risky, _safe, patches = self._release_scenario()
        solver = agent.Agent("")
        with (
            patches[0], patches[1], patches[2],
            patches[3], patches[4], patches[5], patches[6],
            mock.patch.object(agent, "RELEASE_RISK_SHADOW_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_RERANK_LAMBDA", 10.0),
        ):
            action = solver.policy(observation)

        # The real action is still the baseline (higher raw score) choice.
        np.testing.assert_allclose(
            action["place_pos"][:2], risky.center[:2], atol=1e-6
        )
        record = solver.last_candidate_diagnostics["shadow_rerank"]
        self.assertTrue(record["applies"])
        self.assertTrue(record["changed"])
        self.assertEqual(record["baseline"]["kind"], "release_candidate")
        self.assertAlmostEqual(record["baseline"]["p_rot"], 0.9)
        self.assertAlmostEqual(
            record["risk_selection"]["center"][0], 0.3
        )
        self.assertAlmostEqual(record["risk_selection"]["p_rot"], 0.05)
        self.assertAlmostEqual(
            record["risk_selection"]["score"], 8.0 - 10.0 * 0.05
        )

    def test_shadow_rerank_skips_second_search_for_settled_choice(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        item = sample_item(0, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        settled = agent.AABB((0.0, 0.0, 0.1), (0.2, 0.2, 0.2),
                             "settled_candidate")

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] != "release":
                yield settled

        solver = agent.Agent("")
        with (
            mock.patch.object(
                agent.CandidateGenerator, "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent, "RELEASE_RISK_SHADOW_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_LIVE_RERANK", False),
        ):
            solver.policy(observation)

        record = solver.last_candidate_diagnostics["shadow_rerank"]
        self.assertFalse(record["applies"])
        self.assertFalse(record["changed"])
        self.assertEqual(
            record["risk_selection"], record["baseline"]
        )

    def test_shadow_rerank_disabled_leaves_no_diagnostics(self):
        observation, _risky, _safe, patches = self._release_scenario()
        solver = agent.Agent("")
        with patches[0], patches[1], patches[2], \
                patches[3], patches[4], patches[5], patches[6]:
            solver.policy(observation)
        self.assertNotIn(
            "shadow_rerank", solver.last_candidate_diagnostics
        )


class MechanicsRiskModelTests(unittest.TestCase):
    def test_parity_with_offline_implementation(self):
        import scripts.evaluate_mechanics_features as emf

        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        scenarios = [
            (container, 0.0, 0.0, 0.3, (0.4, 0.3, 0.2)),
            (container, 0.1, -0.05, 0.6, (0.4, 0.3, 0.2)),
        ]
        offset = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        offset["packed_items"] = [
            {
                "index": 99,
                "length": 0.4,
                "width": 0.4,
                "height": 0.3,
                "orientation": 0,
                "is_soft": False,
                "is_prioritized": False,
                "pos": [0.3, 0.0, 0.19],
                "orn": [0.0, 0.0, 0.0, 1.0],
            }
        ]
        scenarios.append((offset, 0.1, 0.0, 0.6, (0.4, 0.3, 0.2)))
        for scenario_container, x, y, z, dims in scenarios:
            live = agent.release_mechanics_features(
                x, y, z, dims, scenario_container
            )
            offline = emf.mechanics_features(
                agent, scenario_container, x, y, z, dims
            )
            for key in (
                "d_min",
                "theta_c_min",
                "B_min",
                "log1p_eta_max",
                "drop_meters",
                "z_rest",
            ):
                self.assertAlmostEqual(
                    live[key], offline[key], places=9, msg=key
                )
            self.assertEqual(
                live["degenerate_contact"], offline["degenerate_contact"]
            )

    def test_mech_probability_rises_with_drop(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        dims = (0.4, 0.3, 0.2)
        low = agent.release_rotation_risk_probability_mech(
            0.0, 0.0, 0.20, dims, container
        )
        high = agent.release_rotation_risk_probability_mech(
            0.0, 0.0, 0.80, dims, container
        )
        self.assertGreater(high, low)
        self.assertTrue(0.0 <= low <= 1.0)
        self.assertTrue(0.0 <= high <= 1.0)

    def test_risk_adjusted_score_dispatches_to_mech_model(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        candidate = agent.AABB(
            (0.0, 0.0, 0.3), (0.4, 0.3, 0.2), "release_candidate"
        )
        with (
            mock.patch.object(agent, "RELEASE_RISK_P_MODEL", "mech"),
            mock.patch.object(
                agent,
                "release_rotation_risk_probability_mech",
                return_value=0.25,
            ) as mech,
            mock.patch.object(
                agent, "release_rotation_risk_probability"
            ) as static,
            mock.patch.object(agent, "RELEASE_RISK_SLIDE_LAMBDA", 0.0),
        ):
            adjusted, probability = agent.risk_adjusted_score(
                10.0, candidate, None, container, 0, 2.0
            )
        self.assertAlmostEqual(adjusted, 10.0 - 2.0 * 0.25)
        self.assertAlmostEqual(probability, 0.25)
        mech.assert_called_once()
        static.assert_not_called()


class PackedAabbCacheTests(unittest.TestCase):
    def _container_with_boxes(self, count):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            {
                "index": i,
                "length": 0.2,
                "width": 0.2,
                "height": 0.2,
                "orientation": 0,
                "is_soft": False,
                "is_prioritized": False,
                "pos": [0.25 * i, 0.0, 0.14],
                "orn": [0.0, 0.0, 0.0, 1.0],
            }
            for i in range(count)
        ]
        return container

    def test_repeat_calls_reuse_cached_boxes(self):
        container = self._container_with_boxes(2)
        first = agent.packed_aabbs_local(container)
        second = agent.packed_aabbs_local(container)
        self.assertIs(first, second)
        self.assertEqual(len(first), 2)

    def test_append_invalidates_cache(self):
        container = self._container_with_boxes(2)
        first = agent.packed_aabbs_local(container)
        container["packed_items"].append(
            dict(container["packed_items"][0], index=9, pos=[0.6, 0.3, 0.14])
        )
        second = agent.packed_aabbs_local(container)
        self.assertIsNot(first, second)
        self.assertEqual(len(second), 3)

    def test_new_list_object_invalidates_cache(self):
        container = self._container_with_boxes(1)
        first = agent.packed_aabbs_local(container)
        container["packed_items"] = list(container["packed_items"])
        second = agent.packed_aabbs_local(container)
        self.assertIsNot(first, second)
        self.assertEqual(len(second), 1)


class SlideRiskModelTests(unittest.TestCase):
    def test_geometric_parity_with_offline_implementation(self):
        import scripts.evaluate_slide_equivariant as ese

        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = [
            {
                "index": 99,
                "length": 0.4,
                "width": 0.4,
                "height": 0.3,
                "orientation": 0,
                "is_soft": False,
                "is_prioritized": False,
                "pos": [0.3, 0.0, 0.19],
                "orn": [0.0, 0.0, 0.0, 1.0],
            }
        ]
        dims = (0.4, 0.3, 0.2)
        item = {
            "length": dims[0],
            "width": dims[1],
            "height": dims[2],
            "mass": 2.0,
            "lateralFriction": 0.4,
            "is_soft": False,
        }
        candidate = agent.AABB((0.15, 0.0, 0.6), dims, "release_candidate")
        live = agent.release_slide_features(candidate, item, container, 0)
        offline_row = {
            "center": [0.15, 0.0, 0.6],
            "size": list(dims),
            "snapshot_id": "s",
            "case_id": "b000-k20",
            "phi_modelling": {
                "support_ratio": 0.5,
                "com_margin": 0.1,
                "drop_normalized": 0.1,
                "support_imbalance": 0.0,
                "left_right_imbalance": 0.0,
                "front_back_imbalance": 0.0,
            },
            "physical": {
                "settle_metrics": {
                    "settle_displacement_xyz": [0.0, 0.0, 0.0]
                }
            },
            "_item": item,
        }
        offline = ese.frame_row(agent, offline_row, container)
        for key in (
            "com_offset",
            "downhill_margin",
            "uphill_margin",
            "d_min",
            "B_min",
            "log1p_eta_max",
            "drop_meters",
            "mass",
            "lateral_friction",
            "density",
            "is_soft",
        ):
            self.assertAlmostEqual(
                live[key], offline["features"][key], places=9, msg=key
            )
        self.assertTrue(0.0 <= live["support_ratio"] <= 1.0)

    def test_probability_falls_with_friction(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        dims = (0.4, 0.3, 0.2)
        candidate = agent.AABB((0.1, 0.0, 0.3), dims, "release_candidate")

        def item(friction):
            return {
                "length": dims[0],
                "width": dims[1],
                "height": dims[2],
                "mass": 2.0,
                "lateralFriction": friction,
                "is_soft": False,
            }

        slippery = agent.release_large_slide_probability(
            candidate, item(0.1), container, 0
        )
        grippy = agent.release_large_slide_probability(
            candidate, item(0.9), container, 0
        )
        self.assertGreater(slippery, grippy)
        self.assertTrue(0.0 <= grippy <= slippery <= 1.0)

    def test_risk_adjusted_score_includes_slide_term_when_enabled(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        candidate = agent.AABB(
            (0.0, 0.0, 0.3), (0.4, 0.3, 0.2), "release_candidate"
        )
        with (
            mock.patch.object(agent, "RELEASE_RISK_P_MODEL", "mech"),
            mock.patch.object(
                agent,
                "release_rotation_risk_probability_mech",
                return_value=0.2,
            ),
            mock.patch.object(
                agent,
                "release_large_slide_probability",
                return_value=0.5,
            ),
            mock.patch.object(agent, "RELEASE_RISK_SLIDE_LAMBDA", 2.0),
        ):  # noqa: explicit slide lambda regardless of shipped default
            adjusted, p_rot = agent.risk_adjusted_score(
                10.0, candidate, None, container, 0, 1.0
            )
        self.assertAlmostEqual(adjusted, 10.0 - 1.0 * 0.2 - 2.0 * 0.5)
        self.assertAlmostEqual(p_rot, 0.2)

    def test_slide_shadow_runs_under_live_rerank_and_restores_lambda(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        item = sample_item(0, length=0.2, width=0.2, height=0.2)
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        slidey = agent.AABB((0.0, 0.0, 0.2), (0.2, 0.2, 0.2),
                            "release_candidate")
        steady = agent.AABB((0.3, 0.0, 0.2), (0.2, 0.2, 0.2),
                            "release_candidate")

        def attempts(*_args, **kwargs):
            if kwargs["attempt_kind"] == "release":
                yield slidey
                yield steady

        def score(candidate, *_args):
            return 10.0 if candidate.center[0] == 0.0 else 8.0

        def slide_probability(candidate, *_a, **_k):
            return 0.9 if candidate.center[0] == 0.0 else 0.05

        solver = agent.Agent("")
        with (
            mock.patch.object(
                agent.CandidateGenerator, "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(agent.Ranker, "score", side_effect=score),
            mock.patch.object(agent, "RELEASE_RISK_P_MODEL", "mech"),
            mock.patch.object(
                agent,
                "release_rotation_risk_probability_mech",
                return_value=0.1,
            ),
            mock.patch.object(
                agent,
                "release_large_slide_probability",
                side_effect=slide_probability,
            ),
            mock.patch.object(agent, "RELEASE_RISK_LIVE_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_SHADOW_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_RERANK_LAMBDA", 1.0),
            mock.patch.object(
                agent, "RELEASE_RISK_SLIDE_SHADOW_LAMBDA", 5.0
            ),
            mock.patch.object(agent, "RELEASE_RISK_SLIDE_LAMBDA", 0.0),
        ):
            action = solver.policy(observation)
            restored = agent.RELEASE_RISK_SLIDE_LAMBDA

        # Live action is rot-only (equal p_rot): the higher score wins.
        np.testing.assert_allclose(
            action["place_pos"][:2], slidey.center[:2], atol=1e-6
        )
        record = solver.last_candidate_diagnostics["shadow_rerank"]
        self.assertAlmostEqual(record["slide_lambda"], 5.0)
        self.assertTrue(record["changed"])
        self.assertAlmostEqual(
            record["risk_selection"]["center"][0], 0.3
        )
        # The live slide lambda is restored after the shadow pass.
        self.assertEqual(restored, 0.0)


class LiveRerankTests(unittest.TestCase):
    def test_submission_defaults_are_risk_on_mech_lambda1(self):
        # Frozen by the 2026-07-31 final_holdout evaluation (protocol
        # section 8). A failure here means the submission default moved.
        self.assertTrue(agent.RELEASE_RISK_LIVE_RERANK)
        self.assertEqual(agent.RELEASE_RISK_P_MODEL, "mech")
        self.assertAlmostEqual(agent.RELEASE_RISK_RERANK_LAMBDA, 1.0)
        self.assertAlmostEqual(agent.RELEASE_RISK_SLIDE_LAMBDA, 0.5)

    def test_live_rerank_changes_the_real_action(self):
        observation, _risky, safe, patches = (
            ShadowRerankTests._release_scenario(self)
        )
        solver = agent.Agent("")
        with (
            patches[0], patches[1], patches[2],
            patches[3], patches[4], patches[5], patches[6],
            mock.patch.object(agent, "RELEASE_RISK_LIVE_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_RERANK_LAMBDA", 10.0),
        ):
            action = solver.policy(observation)

        # With the risk term live, the safe candidate wins the real action.
        np.testing.assert_allclose(
            action["place_pos"][:2], safe.center[:2], atol=1e-6
        )
        record = solver.last_candidate_diagnostics[
            "release_risk_live_rerank"
        ]
        self.assertAlmostEqual(record["lambda"], 10.0)

    def test_live_rerank_suppresses_shadow_record(self):
        observation, _risky, _safe, patches = (
            ShadowRerankTests._release_scenario(self)
        )
        solver = agent.Agent("")
        with (
            patches[0], patches[1], patches[2],
            patches[3], patches[4], patches[5], patches[6],
            mock.patch.object(agent, "RELEASE_RISK_LIVE_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_SHADOW_RERANK", True),
            mock.patch.object(agent, "RELEASE_RISK_RERANK_LAMBDA", 10.0),
        ):
            solver.policy(observation)
        self.assertNotIn(
            "shadow_rerank", solver.last_candidate_diagnostics
        )

    def test_live_rerank_off_keeps_baseline_action(self):
        observation, risky, _safe, patches = (
            ShadowRerankTests._release_scenario(self)
        )
        solver = agent.Agent("")
        with patches[0], patches[1], patches[2], \
                patches[3], patches[4], patches[5], patches[6]:
            action = solver.policy(observation)
        np.testing.assert_allclose(
            action["place_pos"][:2], risky.center[:2], atol=1e-6
        )
        self.assertNotIn(
            "release_risk_live_rerank", solver.last_candidate_diagnostics
        )


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
        # Both branches of the attempt budget must place through the common
        # core. 0 is the legacy global-deadline scan kept as the escape
        # hatch; the shipped default is the adopted bounded budget. Naming
        # them here keeps the legacy path covered now that it is no longer
        # what an unconfigured evaluator does.
        for attempts in (0, agent.OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM):
            with self.subTest(attempts_per_item=attempts):
                container = sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
                container["volume"] = 4.0
                evaluator = agent.DryRunEvaluator(
                    [container], attempts_per_item=attempts
                )
                items = [sample_item(0), sample_item(1)]

                result = evaluator.evaluate(items)

                self.assertEqual(result.placed_count, 2)
                self.assertIsNone(result.failed_index)
                self.assertGreater(result.fill_ratio, 0.0)
                self.assertGreaterEqual(
                    result.mean_support_ratio, agent.MIN_SUPPORT_RATIO
                )

    def test_offline_defaults_ship_the_adopted_bounded_rollout(self):
        """
        ADR-002 adoption, from Actions run 30717998654. These are shipped
        submission defaults, not experiment settings, so pin them: a silent
        revert to the legacy 0/0.0 costs five physical placements on the
        bundled Task A case and is invisible in every unit test otherwise.
        """
        self.assertEqual(agent.OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM, 128)
        self.assertEqual(agent.OFFLINE_PAIR_MACRO_BUDGET_SECONDS, 0.5)
        self.assertFalse(agent.OFFLINE_RISK_RERANK)

    def test_unconfigured_dry_run_uses_the_shipped_attempt_budget(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        evaluator = agent.DryRunEvaluator([container])

        self.assertEqual(
            evaluator.attempts_per_item,
            agent.OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM,
        )

        with (
            mock.patch.object(
                agent.PlacementCore, "rescue_choose", return_value=None
            ) as bounded_choose,
            mock.patch.object(agent.PlacementCore, "choose") as unbounded,
        ):
            evaluator.evaluate([sample_item(0)])

        unbounded.assert_not_called()
        self.assertEqual(
            bounded_choose.call_args.kwargs["attempt_budget"],
            agent.OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM,
        )

    def test_zero_attempts_restores_the_legacy_unbounded_scan(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        evaluator = agent.DryRunEvaluator(
            [container], attempts_per_item=0
        )

        with (
            mock.patch.object(
                agent.PlacementCore, "choose", return_value=None
            ) as unbounded,
            mock.patch.object(
                agent.PlacementCore, "rescue_choose"
            ) as bounded_choose,
        ):
            evaluator.evaluate([sample_item(0)])

        bounded_choose.assert_not_called()
        unbounded.assert_called_once()

    def test_dry_run_forwards_explicit_risk_lambda_to_both_scan_paths(self):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        for attempts, method_name in ((0, "choose"), (37, "rescue_choose")):
            with self.subTest(attempts=attempts):
                evaluator = agent.DryRunEvaluator(
                    [container], attempts_per_item=attempts, risk_lambda=1.25
                )
                with mock.patch.object(
                    agent.PlacementCore, method_name, return_value=None
                ) as choose:
                    evaluator.evaluate([sample_item(0)])

                self.assertEqual(choose.call_args.kwargs["risk_lambda"], 1.25)

    def test_bounded_dry_run_uses_deterministic_attempt_budget(self):
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        items = [sample_item(0), sample_item(1)]
        decisions = [
            agent.PlacementDecision(
                action={
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": np.zeros(3, dtype=np.float32),
                    "orientation": 0,
                },
                candidate=agent.AABB(
                    (0.0, 0.0, 0.1),
                    (0.2, 0.2, 0.2),
                    "candidate",
                ),
                score=1.0,
            ),
            None,
        ]
        evaluator = agent.DryRunEvaluator(
            [container], attempts_per_item=37
        )
        with (
            mock.patch.object(
                agent.PlacementCore,
                "rescue_choose",
                side_effect=decisions,
            ) as bounded_choose,
            mock.patch.object(
                agent.PlacementCore,
                "choose",
            ) as unbounded_choose,
        ):
            result = evaluator.evaluate(items)

        self.assertEqual(result.placed_count, 1)
        self.assertEqual(result.failed_index, 1)
        self.assertEqual(bounded_choose.call_count, 2)
        self.assertEqual(
            [
                call.kwargs["attempt_budget"]
                for call in bounded_choose.call_args_list
            ],
            [37, 37],
        )
        unbounded_choose.assert_not_called()

    def test_offline_budget_never_reaches_the_online_policy(self):
        """
        The adoption is Task-A-only. That claim rests entirely on the
        offline budget being read nowhere but the dry-run evaluator, so
        assert it rather than restating it: a Task B/C observation
        (optimize false, the harness never calls optimize) must produce an
        action without constructing an evaluator at all.
        """
        solver = agent.Agent("")
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        solver.get_init_states(
            {"optimize": False, "container_list": [container]}
        )
        observation = {
            "pool_list": [sample_item(0), sample_item(1)],
            "container_list": [container],
        }

        with mock.patch.object(
            agent, "DryRunEvaluator", side_effect=AssertionError
        ) as evaluator:
            action = solver.policy(observation)

        evaluator.assert_not_called()
        self.assertIsNotNone(action)

    def test_optimize_reports_the_shipped_budget_it_actually_used(self):
        solver = agent.Agent("")
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        solver.get_init_states(
            {"optimize": True, "container_list": [container]}
        )
        solver._offline_search_budget_seconds = 0.0
        items = [sample_item(0), sample_item(1)]

        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "trace.jsonl"
            solver._policy_trace_path = str(trace_path)
            solver.optimize(items)
            record = json.loads(
                trace_path.read_text(encoding="utf-8").splitlines()[-1]
            )

        self.assertEqual(
            record["dry_run_attempts_per_item"],
            agent.OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM,
        )
        self.assertEqual(
            record["pair_macro_budget_seconds"],
            agent.OFFLINE_PAIR_MACRO_BUDGET_SECONDS,
        )

    def test_optimize_emits_offline_diagnostics(self):
        solver = agent.Agent("")
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        solver.get_init_states(
            {"optimize": True, "container_list": [container]}
        )
        solver._offline_search_budget_seconds = 0.0
        items = [sample_item(0), sample_item(1)]

        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "trace.jsonl"
            solver._policy_trace_path = str(trace_path)
            order = solver.optimize(items)
            records = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(records[-1]["event"], "offline_optimization")
        self.assertEqual(records[-1]["optimized_order"], order)
        self.assertIn("best_result", records[-1])

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


class RescueScanTests(unittest.TestCase):
    def test_visible_items_are_round_robin_by_class(self):
        pool = [sample_item(index) for index in range(3)]
        pool.extend(
            [
                sample_item(3, is_soft=True),
                sample_item(4, is_soft=True),
                sample_item(5, is_prioritized=True),
            ]
        )

        ordered = agent.rescue_online_items(pool)

        self.assertEqual(
            [agent.item_class_name(item) for _index, item in ordered],
            ["normal", "soft", "priority", "normal", "soft", "normal"],
        )
        self.assertEqual({index for index, _item in ordered}, set(range(6)))

    def test_rescue_units_cover_both_modes_per_item_before_deepening(self):
        items = [(0, sample_item(0)), (1, sample_item(1))]
        observation = {
            "pool_list": [item for _index, item in items],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }

        units = agent.rescue_search_units(observation, items)

        self.assertEqual(
            [(unit[4], unit[8]) for unit in units[:4]],
            [
                (0, "release"),
                (1, "release"),
                (0, "settled"),
                (1, "settled"),
            ],
        )

    def test_rescue_keeps_best_incumbent_but_prefers_settled(self):
        item = sample_item(0)
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        observation = {
            "pool_list": [item],
            "container_list": [container],
        }
        units = [
            (0, 0, 0, 0, 0, item, 0, 0, "settled"),
            (0, 0, 0, 1, 0, item, 0, 0, "release"),
        ]
        settled = agent.AABB(
            (0.1, 0.0, 0.1), (0.2, 0.2, 0.2), "candidate"
        )
        release = agent.AABB(
            (0.9, 0.0, 0.2),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )

        def attempts(*_args, **kwargs):
            return iter(
                [release]
                if kwargs["attempt_kind"] == "release"
                else [settled]
            )

        diagnostics = {}
        with (
            mock.patch.object(
                agent, "rescue_search_units", return_value=units
            ),
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                side_effect=attempts,
            ),
            mock.patch.object(
                agent.Ranker,
                "score",
                side_effect=lambda candidate, *_args: float(
                    candidate.center[0]
                ),
            ),
        ):
            decision = agent.PlacementCore.rescue_choose(
                observation,
                [(0, item)],
                deadline=time.perf_counter() + 1.0,
                attempt_budget=8,
                diagnostics=diagnostics,
            )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.candidate.name, "candidate")
        self.assertEqual(diagnostics["rescue_scan"]["attempts"], 2)
        self.assertEqual(
            diagnostics["rescue_scan"]["accepted_release"], 1
        )
        self.assertEqual(
            diagnostics["rescue_scan"]["accepted_settled"], 1
        )

    def test_policy_reserves_time_and_returns_rescue_action(self):
        item = sample_item(0)
        observation = {
            "pool_list": [item],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        candidate = agent.AABB(
            (0.2, 0.0, 0.2),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )
        rescue_decision = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.array([0.2, 0.0, 0.2], dtype=np.float32),
                "orientation": 0,
            },
            candidate=candidate,
            score=1.0,
        )
        observed_deadlines = []

        def no_closed_loop(
            _self,
            _observation,
            _pool_list,
            _ordered_items,
            deadline,
            **_kwargs,
        ):
            observed_deadlines.append(deadline)
            return None

        with (
            mock.patch.object(agent, "RESCUE_SCAN_ENABLED", True),
            mock.patch.object(agent, "RESCUE_SCAN_RESERVE_SECONDS", 0.9),
            mock.patch.object(agent.time, "perf_counter", return_value=100.0),
            mock.patch.object(
                agent.Agent,
                "_closed_loop_choice",
                autospec=True,
                side_effect=no_closed_loop,
            ),
            mock.patch.object(
                agent.PlacementCore, "choose", return_value=None
            ),
            mock.patch.object(
                agent.PlacementCore,
                "rescue_choose",
                return_value=rescue_decision,
            ) as rescue,
        ):
            solver = agent.Agent("")
            action = solver.policy(observation)

        self.assertEqual(observed_deadlines, [105.6])
        self.assertEqual(rescue.call_args.kwargs["deadline"], 106.5)
        np.testing.assert_array_equal(
            action["place_pos"], rescue_decision.action["place_pos"]
        )
        self.assertEqual(solver.last_action_source, "rescue_scan")

    def test_disabled_policy_never_calls_rescue(self):
        observation = {
            "pool_list": [sample_item(0)],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        with (
            mock.patch.object(agent, "RESCUE_SCAN_ENABLED", False),
            mock.patch.object(
                agent.Agent, "_closed_loop_choice", return_value=None
            ),
            mock.patch.object(
                agent.PlacementCore, "choose", return_value=None
            ),
            mock.patch.object(agent.PlacementCore, "rescue_choose") as rescue,
        ):
            action = agent.Agent("").policy(observation)

        rescue.assert_not_called()
        self.assertEqual(action["place_pos"].tolist(), [0.0, 0.0, 0.25])


class CrossStepIncumbentTests(unittest.TestCase):
    def test_collector_keeps_top_n_per_item_and_candidate_kind(self):
        item = sample_item(42)
        collector = agent.CrossStepCandidateCollector(per_item=2)

        def observe(score, x, kind="candidate"):
            candidate = agent.AABB(
                (x, 0.0, 0.2), (0.2, 0.2, 0.2), kind
            )
            decision = agent.PlacementDecision(
                action={
                    "item_idx": 3,
                    "container_idx": 0,
                    "place_pos": np.array(
                        [x, 0.0, 0.2], dtype=np.float32
                    ),
                    "orientation": 0,
                },
                candidate=candidate,
                score=score,
            )
            collector.observe(3, item, 0, 0, decision)

        observe(1.0, 0.1)
        observe(3.0, 0.3)
        observe(2.0, 0.2)
        observe(3.0, 0.3)  # duplicate command is not counted twice
        observe(0.5, 0.4, "release_candidate")

        retained = collector.snapshot()

        self.assertEqual(len(retained), 3)
        self.assertEqual(
            sorted(
                candidate.previous_score
                for candidate in retained
                if candidate.candidate.name == "candidate"
            ),
            [2.0, 3.0],
        )
        self.assertEqual(
            [
                candidate.previous_score
                for candidate in retained
                if candidate.candidate.name == "release_candidate"
            ],
            [0.5],
        )

    def test_revalidation_remaps_stable_item_index_to_current_pool(self):
        item = sample_item(42)
        container = sample_container(
            require_shelf=False,
            center_x=0.0,
            cut_x=0.0,
        )
        candidate = agent.AABB(
            (0.0, 0.0, 0.2), (0.2, 0.2, 0.2), "candidate"
        )
        retained = agent.CrossStepCandidate(
            item_index=42,
            previous_pool_index=7,
            container_index=0,
            orientation=0,
            candidate=candidate,
            previous_score=1.5,
        )

        with mock.patch.object(
            agent.Geometry, "rejection_reason", return_value=None
        ):
            summary, valid = agent.revalidate_cross_step_candidates(
                {
                    "pool_list": [sample_item(99), item],
                    "container_list": [container],
                },
                [retained],
            )

        self.assertEqual(summary["static_valid_count"], 1)
        self.assertEqual(summary["pool_survivor_item_count"], 1)
        self.assertEqual(valid[0].action["item_idx"], 1)
        self.assertEqual(
            summary["candidates"][0]["current_pool_index"], 1
        )

    def test_shadow_records_rescue_opportunity_without_using_it(self):
        item = sample_item(42)
        observation = {
            "pool_list": [item],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        candidate = agent.AABB(
            (0.2, 0.0, 0.2),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )
        retained = agent.CrossStepCandidate(
            item_index=42,
            previous_pool_index=1,
            container_index=0,
            orientation=0,
            candidate=candidate,
            previous_score=1.0,
        )
        valid_decision = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.array(
                    [0.2, 0.0, 0.2], dtype=np.float32
                ),
                "orientation": 0,
            },
            candidate=candidate,
            score=1.0,
        )

        solver = agent.Agent("")
        solver._cross_step_candidates = [retained]
        with (
            mock.patch.object(agent, "CROSS_STEP_INCUMBENT_MODE", "shadow"),
            mock.patch.object(
                agent.Agent, "_closed_loop_choice", return_value=None
            ),
            mock.patch.object(
                agent.PlacementCore, "choose", return_value=None
            ),
            mock.patch.object(
                agent,
                "revalidate_cross_step_candidates",
                return_value=(
                    {
                        "mode": "shadow",
                        "static_valid_count": 1,
                    },
                    [valid_decision],
                ),
            ),
        ):
            action = solver.policy(observation)

        self.assertEqual(action["place_pos"].tolist(), [0.0, 0.0, 0.25])
        self.assertEqual(solver.last_action_source, "unsafe_protocol_fallback")
        self.assertTrue(
            solver.last_candidate_diagnostics["cross_step_incumbent"][
                "would_prevent_protocol_fallback"
            ]
        )
        self.assertEqual(solver.last_cross_step_valid_decisions, [valid_decision])

    def test_mode_off_does_not_attach_candidate_observer(self):
        observation = {
            "pool_list": [sample_item(0)],
            "container_list": [
                sample_container(
                    require_shelf=False,
                    center_x=0.0,
                    cut_x=0.0,
                )
            ],
        }
        seen = {}

        def closed_loop(_self, *_args, **kwargs):
            seen["observer"] = kwargs.get("candidate_observer")
            return None

        with (
            mock.patch.object(agent, "CROSS_STEP_INCUMBENT_MODE", "off"),
            mock.patch.object(
                agent, "VISIBLE_POOL_ROLLOUT_MODE", "off"
            ),
            # The shipped guard_quiet default materializes the observed
            # pool (and so an observer) on its own; this test pins the
            # no-observer contract of the remaining modes.
            mock.patch.object(agent, "PHYSICS_PROBE_MODE", "off"),
            mock.patch.object(
                agent, "visible_pool_rollout_evaluation"
            ) as rollout_shadow,
            mock.patch.object(
                agent, "temporal_chunk_ensemble_evaluation"
            ) as temporal_shadow,
            mock.patch.object(
                agent, "build_temporal_chunk_proposals"
            ) as temporal_build,
            mock.patch.object(
                agent.Agent,
                "_closed_loop_choice",
                autospec=True,
                side_effect=closed_loop,
            ),
            mock.patch.object(
                agent.PlacementCore, "choose", return_value=None
            ) as choose,
        ):
            solver = agent.Agent("")
            solver.policy(observation)

        self.assertIsNone(seen["observer"])
        self.assertNotIn("candidate_observer", choose.call_args.kwargs)
        self.assertNotIn(
            "cross_step_incumbent", solver.last_candidate_diagnostics
        )
        rollout_shadow.assert_not_called()
        temporal_shadow.assert_not_called()
        temporal_build.assert_not_called()
        self.assertNotIn(
            "temporal_chunk_ensemble", solver.last_candidate_diagnostics
        )

    def test_temporal_chunk_builds_future_offsets_and_stops_at_release(self):
        pool = [sample_item(10), sample_item(20), sample_item(30)]
        observation = {
            "pool_list": pool,
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }

        def decision(pool_index, kind, score):
            candidate = agent.AABB(
                (0.1 + pool_index * 0.2, 0.0, 0.1),
                (0.2, 0.2, 0.2),
                kind,
            )
            return agent.PlacementDecision(
                action={
                    "item_idx": pool_index,
                    "container_idx": 0,
                    "place_pos": np.asarray(
                        candidate.center, dtype=np.float32
                    ),
                    "orientation": 0,
                },
                candidate=candidate,
                score=score,
            )

        initial = decision(0, "candidate", 3.0)
        future_settled = decision(1, "candidate", 2.0)
        future_release = decision(2, "release_candidate", 1.0)
        with (
            mock.patch.object(agent, "apply_placement_decision"),
            mock.patch.object(
                agent,
                "bounded_rollout_decision",
                side_effect=[
                    (future_settled, 12, 3),
                    (future_release, 8, 2),
                ],
            ),
        ):
            summary, proposals = agent.build_temporal_chunk_proposals(
                observation,
                list(enumerate(pool)),
                initial,
                origin_step=7,
                depth=4,
            )

        self.assertEqual([p.target_step for p in proposals], [8, 9])
        self.assertEqual([p.item_index for p in proposals], [20, 30])
        self.assertEqual(
            proposals[-1].candidate.name, "release_candidate"
        )
        self.assertEqual(summary["attempts_used"], 20)
        self.assertEqual(summary["accepted_candidates"], 5)
        self.assertEqual(
            summary["terminal_reason"], "release_transition_uncertain"
        )

    def test_temporal_chunk_ensembles_matching_delays_after_revalidation(self):
        item = sample_item(42)
        observation = {
            "pool_list": [sample_item(99), item],
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }
        candidate_a = agent.AABB(
            (0.201, 0.001, 0.1), (0.2, 0.2, 0.2), "candidate"
        )
        candidate_b = agent.AABB(
            (0.204, 0.004, 0.1), (0.2, 0.2, 0.2), "candidate"
        )
        proposals = [
            agent.TemporalChunkProposal(
                origin_step=3,
                target_step=5,
                item_index=42,
                previous_pool_index=0,
                container_index=0,
                orientation=0,
                candidate=candidate_a,
                previous_score=1.0,
            ),
            agent.TemporalChunkProposal(
                origin_step=4,
                target_step=5,
                item_index=42,
                previous_pool_index=0,
                container_index=0,
                orientation=0,
                candidate=candidate_b,
                previous_score=1.2,
            ),
        ]
        selected = agent.PlacementDecision(
            action={
                "item_idx": 1,
                "container_idx": 0,
                "place_pos": np.asarray(candidate_a.center, dtype=np.float32),
                "orientation": 0,
            },
            candidate=candidate_a,
            score=1.1,
        )

        with mock.patch.object(
            agent.Geometry, "rejection_reason", return_value=None
        ):
            record, valid = agent.temporal_chunk_ensemble_evaluation(
                observation,
                proposals,
                selected,
                current_step=5,
                cell_size=0.1,
            )

        self.assertEqual(len(valid), 2)
        self.assertEqual(record["origin_count"], 2)
        self.assertEqual(record["valid_origin_count"], 2)
        self.assertEqual(record["max_vote_count"], 2)
        self.assertEqual(record["scheduled_by_delay"], {"2": 1, "1": 1})
        self.assertEqual(record["valid_by_delay"], {"2": 1, "1": 1})
        self.assertTrue(record["selected_matches_consensus"])
        self.assertTrue(record["selected_matches_any_valid_action"])
        self.assertTrue(record["selected_matches_any_valid_item"])
        self.assertEqual(record["item_group_count"], 1)
        self.assertEqual(record["max_item_vote_count"], 2)
        self.assertEqual(record["item_consensus"]["item_index"], 42)
        self.assertTrue(record["selected_matches_item_consensus"])
        self.assertFalse(record["would_prevent_protocol_fallback"])

    def test_temporal_chunk_shadow_records_without_changing_action(self):
        pool = [sample_item(0), sample_item(1)]
        observation = {
            "pool_list": pool,
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }
        candidate = agent.AABB(
            (0.2, 0.0, 0.1), (0.2, 0.2, 0.2), "candidate"
        )
        selected = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.asarray(candidate.center, dtype=np.float32),
                "orientation": 0,
            },
            candidate=candidate,
            score=1.0,
        )
        future = agent.TemporalChunkProposal(
            origin_step=0,
            target_step=1,
            item_index=1,
            previous_pool_index=1,
            container_index=0,
            orientation=0,
            candidate=candidate,
            previous_score=0.5,
        )
        with (
            mock.patch.object(
                agent, "TEMPORAL_CHUNK_ENSEMBLE_MODE", "shadow"
            ),
            mock.patch.object(
                agent, "CROSS_STEP_INCUMBENT_MODE", "off"
            ),
            mock.patch.object(agent, "VISIBLE_POOL_ROLLOUT_MODE", "off"),
            mock.patch.object(
                agent.Agent, "_closed_loop_choice", return_value=selected
            ),
            mock.patch.object(
                agent,
                "temporal_chunk_ensemble_evaluation",
                return_value=(
                    {"mode": "shadow", "scheduled_count": 0}, []
                ),
            ) as evaluate,
            mock.patch.object(
                agent,
                "build_temporal_chunk_proposals",
                return_value=(
                    {"generated_count": 1, "elapsed_seconds": 0.01},
                    [future],
                ),
            ) as build,
        ):
            solver = agent.Agent("")
            action = solver.policy(observation)

        np.testing.assert_array_equal(action["place_pos"], selected.action["place_pos"])
        evaluate.assert_called_once()
        build.assert_called_once()
        telemetry = solver.last_candidate_diagnostics[
            "temporal_chunk_ensemble"
        ]
        self.assertEqual(telemetry["generated_for_future_count"], 1)
        self.assertEqual(telemetry["pending_target_steps"], [1])
        self.assertEqual(solver._temporal_chunk_proposals, [future])

    def test_temporal_chunk_marks_a_valid_delayed_fallback_alternative(self):
        item = sample_item(42)
        candidate = agent.AABB(
            (0.2, 0.0, 0.1), (0.2, 0.2, 0.2), "candidate"
        )
        proposal = agent.TemporalChunkProposal(
            origin_step=4,
            target_step=5,
            item_index=42,
            previous_pool_index=0,
            container_index=0,
            orientation=0,
            candidate=candidate,
            previous_score=1.0,
        )
        observation = {
            "pool_list": [item],
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }

        with mock.patch.object(
            agent.Geometry, "rejection_reason", return_value=None
        ):
            record, valid = agent.temporal_chunk_ensemble_evaluation(
                observation,
                [proposal],
                None,
                current_step=5,
            )

        self.assertEqual(len(valid), 1)
        self.assertEqual(record["max_item_vote_count"], 1)
        self.assertFalse(record["selected_matches_any_valid_item"])
        self.assertTrue(record["would_prevent_protocol_fallback"])

    def test_rollout_shadow_records_but_does_not_change_action(self):
        item = sample_item(0)
        observation = {
            "pool_list": [item],
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }
        decision = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.array(
                    [0.1, 0.0, 0.1], dtype=np.float32
                ),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.1, 0.0, 0.1),
                (0.2, 0.2, 0.2),
                "candidate",
            ),
            score=1.0,
        )
        shadow = {
            "mode": "shadow",
            "would_change_item": True,
            "proposed_pool_index": 1,
        }
        with (
            mock.patch.object(
                agent, "VISIBLE_POOL_ROLLOUT_MODE", "shadow"
            ),
            mock.patch.object(
                agent.Agent,
                "_closed_loop_choice",
                return_value=decision,
            ),
            mock.patch.object(
                agent,
                "visible_pool_rollout_evaluation",
                return_value=(shadow, decision),
            ) as rollout_shadow,
        ):
            solver = agent.Agent("")
            solver.last_top_candidates = [decision]
            action = solver.policy(observation)

        self.assertEqual(action["item_idx"], 0)
        self.assertEqual(
            solver.last_candidate_diagnostics["visible_pool_rollout"],
            shadow,
        )
        rollout_shadow.assert_called_once()

    def test_rollout_enforce_returns_in_band_proposal(self):
        pool = [sample_item(0), sample_item(1)]
        observation = {
            "pool_list": pool,
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }

        def decision(pool_index, score):
            return agent.PlacementDecision(
                action={
                    "item_idx": pool_index,
                    "container_idx": 0,
                    "place_pos": np.array(
                        [0.1 + pool_index * 0.2, 0.0, 0.1],
                        dtype=np.float32,
                    ),
                    "orientation": 0,
                },
                candidate=agent.AABB(
                    (0.1 + pool_index * 0.2, 0.0, 0.1),
                    (0.2, 0.2, 0.2),
                    "candidate",
                ),
                score=score,
            )

        selected = decision(0, 1.0)
        alternative = decision(1, 0.9)
        values = {
            0: agent.VisiblePoolRolloutValue(
                0, 0.0, 0.0, 0.0, 4, 1, False, False,
                "no_candidate", (),
            ),
            1: agent.VisiblePoolRolloutValue(
                1, 0.1, 0.0, 0.0, 4, 1, False, False,
                "depth_reached", (),
            ),
        }
        with mock.patch.object(
            agent,
            "visible_pool_rollout_value",
            side_effect=lambda _observation, _items, value, **_kwargs: (
                values[int(value.action["item_idx"])]
            ),
        ):
            record, proposed = agent.visible_pool_rollout_evaluation(
                observation,
                list(enumerate(pool)),
                [selected, alternative],
                selected,
                q_band=0.15,
            )

        self.assertIs(proposed, alternative)
        self.assertTrue(record["would_change_item"])
        self.assertTrue(record["proposal_improves_rollout"])
        self.assertTrue(record["unrestricted_proposal_within_q_band"])
        self.assertAlmostEqual(record["unrestricted_proposed_q_loss"], 0.1)

    def test_rollout_enforce_keeps_selected_when_proposal_is_out_of_band(self):
        pool = [sample_item(0), sample_item(1)]
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )

        def decision(pool_index, score):
            return agent.PlacementDecision(
                action={
                    "item_idx": pool_index,
                    "container_idx": 0,
                    "place_pos": np.zeros(3, dtype=np.float32),
                    "orientation": 0,
                },
                candidate=agent.AABB(
                    (pool_index * 0.2, 0.0, 0.1),
                    (0.2, 0.2, 0.2),
                    "candidate",
                ),
                score=score,
            )

        selected = decision(0, 1.0)
        alternative = decision(1, 0.7)
        values = {
            0: agent.VisiblePoolRolloutValue(
                0, 0.0, 0.0, 0.0, 1, 1, False, False,
                "no_candidate", (),
            ),
            1: agent.VisiblePoolRolloutValue(
                2, 0.2, 0.0, 0.0, 1, 1, False, False,
                "depth_reached", (),
            ),
        }
        with mock.patch.object(
            agent,
            "visible_pool_rollout_value",
            side_effect=lambda _observation, _items, value, **_kwargs: (
                values[int(value.action["item_idx"])]
            ),
        ):
            record, proposed = agent.visible_pool_rollout_evaluation(
                {"pool_list": pool, "container_list": [container]},
                list(enumerate(pool)),
                [selected, alternative],
                selected,
                q_band=0.15,
            )

        self.assertIs(proposed, selected)
        self.assertFalse(record["proposal_improves_rollout"])
        self.assertTrue(record["unrestricted_would_change_item"])
        self.assertFalse(record["unrestricted_proposal_within_q_band"])

    def test_initial_release_risk_is_not_double_counted_in_rollout_value(self):
        item = sample_item(0)
        initial = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.0, 0.0, 0.3),
                (0.2, 0.2, 0.2),
                "release_candidate",
            ),
            score=-0.9,
        )
        with mock.patch.object(agent, "apply_placement_decision"):
            value = agent.visible_pool_rollout_value(
                {
                    "pool_list": [item],
                    "container_list": [sample_container()],
                },
                [(0, item)],
                initial,
                depth=1,
            )

        self.assertTrue(value.initial_release_proxy)
        self.assertEqual(value.cumulative_rotation_risk, 0.0)
        self.assertEqual(value.cumulative_slide_risk, 0.0)

    def test_policy_enforce_returns_rollout_proposal(self):
        pool = [sample_item(0), sample_item(1)]
        observation = {
            "pool_list": pool,
            "container_list": [
                sample_container(
                    require_shelf=False, center_x=0.0, cut_x=0.0
                )
            ],
        }

        def decision(pool_index, score):
            return agent.PlacementDecision(
                action={
                    "item_idx": pool_index,
                    "container_idx": 0,
                    "place_pos": np.array(
                        [0.1 + 0.2 * pool_index, 0.0, 0.1],
                        dtype=np.float32,
                    ),
                    "orientation": 0,
                },
                candidate=agent.AABB(
                    (0.1 + 0.2 * pool_index, 0.0, 0.1),
                    (0.2, 0.2, 0.2),
                    "candidate",
                ),
                score=score,
            )

        selected = decision(0, 1.0)
        proposed = decision(1, 0.9)
        for improves_rollout, expected_item in ((True, 1), (False, 0)):
            with self.subTest(improves_rollout=improves_rollout):
                record = {
                    "mode": "enforce",
                    "would_change_item": True,
                    "non_degenerate": True,
                    "proposal_improves_rollout": improves_rollout,
                }
                with (
                    mock.patch.object(
                        agent, "VISIBLE_POOL_ROLLOUT_MODE", "enforce"
                    ),
                    mock.patch.object(
                        agent.Agent,
                        "_closed_loop_choice",
                        return_value=selected,
                    ),
                    mock.patch.object(
                        agent,
                        "visible_pool_rollout_evaluation",
                        return_value=(record, proposed),
                    ),
                ):
                    solver = agent.Agent("")
                    action = solver.policy(observation)

                self.assertEqual(action["item_idx"], expected_item)
                self.assertEqual(
                    solver.last_action_source,
                    (
                        "rollout_enforce"
                        if improves_rollout
                        else "placement_core"
                    ),
                )
                self.assertEqual(
                    solver.last_candidate_diagnostics[
                        "visible_pool_rollout"
                    ]["enforced"],
                    improves_rollout,
                )

    def test_rollout_collector_keeps_best_candidate_per_item(self):
        collector = agent.VisiblePoolRolloutCollector()
        item_a = sample_item(10)
        item_b = sample_item(11)
        item_c = sample_item(12)
        item_c["length"] = 0.37

        def observe(item, score):
            decision = agent.PlacementDecision(
                action={
                    "item_idx": item["index"],
                    "container_idx": 0,
                    "place_pos": np.zeros(3, dtype=np.float32),
                    "orientation": 0,
                },
                candidate=agent.AABB(
                    (0.0, 0.0, 0.1),
                    (0.2, 0.2, 0.2),
                    "candidate",
                ),
                score=score,
            )
            collector.observe(item["index"], item, 0, 0, decision)

        observe(item_a, 1.0)
        observe(item_a, 3.0)
        observe(item_a, 2.0)
        observe(item_b, 2.5)
        observe(item_c, 2.0)

        retained = collector.snapshot()
        self.assertEqual(
            [value.score for value in retained], [3.0, 2.5, 2.0]
        )
        diverse = collector.snapshot(limit=2)
        self.assertEqual([value.score for value in diverse], [3.0, 2.0])

    def test_rollout_shadow_does_not_warm_container_interval_cache(self):
        item = sample_item(0)
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        decision = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.0, 0.0, 0.1),
                (0.2, 0.2, 0.2),
                "candidate",
            ),
            score=0.0,
        )
        value = agent.VisiblePoolRolloutValue(
            0, 0.0, 0.0, 0.0, 0, 0, False, False, "depth_reached", ()
        )

        def rollout(*_args, **_kwargs):
            agent.container_z_interval(0.0, 0.0, (0.2, 0.2, 0.2), container)
            return value

        with (
            mock.patch.object(
                agent, "visible_pool_rollout_value", side_effect=rollout
            ),
            mock.patch.object(
                agent, "_cached_container_z_interval"
            ) as cached,
        ):
            agent.visible_pool_rollout_shadow_record(
                {"pool_list": [item], "container_list": [container]},
                [(0, item)],
                [decision],
                decision,
            )

        cached.assert_not_called()
        self.assertFalse(agent._CONTAINER_Z_INTERVAL_CACHE_BYPASS)

    def test_prioritized_candidates_respects_attempt_budget(self):
        item = sample_item(7)
        candidate = agent.AABB(
            (0.0, 0.0, 0.2), (0.2, 0.2, 0.2), "candidate"
        )
        unit = (0, 0, 0, 0, 0, item, 0, 0, "settled")
        diagnostics = {}
        with (
            mock.patch.object(
                agent, "prioritized_search_units", return_value=[unit]
            ),
            mock.patch.object(
                agent.CandidateGenerator,
                "iter_attempts",
                return_value=iter([candidate] * 5),
            ),
        ):
            found = list(
                agent.iter_prioritized_candidates(
                    {"container_list": [sample_container()]},
                    [(0, item)],
                    diagnostics=diagnostics,
                    attempt_budget=2,
                )
            )

        self.assertEqual(len(found), 2)
        self.assertEqual(diagnostics["search"]["attempts_consumed"], 2)

    def test_bounded_rollout_prefers_settled_before_live_score(self):
        item = sample_item(7)
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        release = agent.AABB(
            (0.0, 0.0, 0.3),
            (0.2, 0.2, 0.2),
            "release_candidate",
        )
        settled = agent.AABB(
            (0.0, 0.0, 0.1), (0.2, 0.2, 0.2), "candidate"
        )
        stream = [
            (0, item, 0, 0, release),
            (0, item, 0, 0, settled),
        ]
        support = agent.SupportMetrics(1.0, 0.1, 1, 1.0)
        with (
            mock.patch.object(
                agent,
                "iter_prioritized_candidates",
                return_value=iter(stream),
            ),
            mock.patch.object(
                agent.Geometry, "support_metrics", return_value=support
            ),
            mock.patch.object(
                agent.Ranker,
                "score",
                side_effect=lambda candidate, *_: (
                    100.0
                    if candidate.name == "release_candidate"
                    else -100.0
                ),
            ),
        ):
            decision, _attempts, accepted = agent.bounded_rollout_decision(
                {
                    "pool_list": [item],
                    "container_list": [container],
                },
                [(0, item)],
                attempt_budget=8,
            )

        self.assertEqual(accepted, 2)
        self.assertEqual(decision.candidate.name, "candidate")

    def test_rollout_marks_initial_proxy_and_stops_at_future_release(self):
        pool = [sample_item(index) for index in range(3)]
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        initial = agent.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.0, 0.0, 0.3),
                (0.2, 0.2, 0.2),
                "release_candidate",
            ),
            score=0.0,
        )
        settled = agent.PlacementDecision(
            action={
                "item_idx": 1,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.0, 0.0, 0.1),
                (0.2, 0.2, 0.2),
                "candidate",
            ),
            score=0.0,
        )
        release = agent.PlacementDecision(
            action={
                "item_idx": 2,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=agent.AABB(
                (0.0, 0.0, 0.3),
                (0.2, 0.2, 0.2),
                "release_candidate",
            ),
            score=0.0,
        )
        with (
            mock.patch.object(agent, "apply_placement_decision"),
            mock.patch.object(
                agent,
                "bounded_rollout_decision",
                side_effect=[(settled, 7, 2), (release, 5, 1)],
            ),
            mock.patch.object(
                agent,
                "release_rotation_risk_probability_mech",
                return_value=0.4,
            ),
            mock.patch.object(
                agent,
                "release_large_slide_probability",
                return_value=0.2,
            ),
        ):
            value = agent.visible_pool_rollout_value(
                {"pool_list": pool, "container_list": [container]},
                list(enumerate(pool)),
                initial,
                depth=3,
                attempts_per_step=16,
            )

        self.assertTrue(value.initial_release_proxy)
        self.assertTrue(value.release_truncated)
        self.assertEqual(value.terminal_reason, "release_transition_uncertain")
        self.assertEqual(value.placed_count, 1)
        self.assertEqual(value.attempts_used, 12)
        self.assertEqual(value.accepted_candidates, 3)
        self.assertAlmostEqual(value.cumulative_rotation_risk, 0.4)


if __name__ == "__main__":
    unittest.main()
