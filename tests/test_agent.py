import importlib.util
import pathlib
import sys
import time
import unittest

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
