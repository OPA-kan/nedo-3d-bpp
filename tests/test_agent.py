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


def _container_planes(container):
    """Boundary planes of a container, built by the simulator's own mesh code.

    Returns ``(points, n_vecs)`` in world coordinates, i.e. exactly what the
    environment puts in the observation.
    """
    import os
    import tempfile

    simulator_src = pathlib.Path(__file__).parents[1] / "simulator" / "src"
    if str(simulator_src) not in sys.path:
        sys.path.insert(0, str(simulator_src))
    from ground_handling.utils import aff, write_open_cut_corner_cup_obj

    with tempfile.TemporaryDirectory() as directory:
        points, normals = write_open_cut_corner_cup_obj(
            os.path.join(directory, "uld.obj"),
            width=container["length"],
            height=container["height"],
            cut_x=container["cut_x"],
            cut_y=container.get("cut_y", 0.4),
            depth=container["width"],
            wall=container["thickness"],
            bottom=container["thickness"],
        )
    rotation = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    offset = (
        container_offset(container),
        0.0,
        container["height"] / 2.0 + container.get("buffer", 0.0),
    )
    return (
        [list(point) for point in aff(points, rotation, offset)],
        [list(normal) for normal in aff(normals, rotation, (0, 0, 0))],
    )


def container_offset(container):
    center = container.get("center")
    return 0.0 if center is None else float(center[0])


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
        """A floor placement keeps the validator's direct-rest path.

        It is commanded FLOOR_ACTION_LIFT above contact — the robot releases
        and the item drops — but that stays inside the validator's 0.05 m
        direct-rest window, so the sweep is *not* raised by
        SIMULATOR_DROP_HEIGHT the way a shelf placement is.
        """
        container = sample_container(require_shelf=False, cut_x=0.0)
        item_height = 0.2
        center_z = container["thickness"] + item_height / 2.0
        candidate = agent.AABB(
            (0.0, 0.0, center_z),
            (0.3, 0.3, item_height),
        )

        sweep = agent.transport_sweep(candidate, container)

        commanded_z = center_z + agent.FLOOR_ACTION_LIFT
        self.assertAlmostEqual(sweep.center[2], commanded_z)
        self.assertLess(agent.FLOOR_ACTION_LIFT, 0.05)
        self.assertLess(
            sweep.center[2], commanded_z + agent.SIMULATOR_DROP_HEIGHT
        )

    def test_floor_placement_is_reachable_at_all(self):
        """Containment is tested on the commanded pose, support on the settled
        one.  Testing both on a single pose is unsatisfiable: the item would
        have to touch the floor and clear it by INCLUSION_CLEARANCE at once,
        which made every floor placement invalid."""
        container = sample_container(require_shelf=False, center_x=0.0)
        container["points"], container["n_vecs"] = _container_planes(container)
        item_height = 0.213
        candidate = agent.AABB(
            (0.5, 0.3, container["thickness"] + item_height / 2.0),
            (0.7, 0.5, item_height),
        )

        self.assertAlmostEqual(
            agent.Geometry.support_ratio(candidate, container), 1.0
        )
        self.assertTrue(agent.Geometry.valid(candidate, container))

        commanded = agent.simulator_action_center(candidate, container)
        self.assertAlmostEqual(
            float(commanded[2]),
            float(candidate.center[2]) + agent.FLOOR_ACTION_LIFT,
        )
        # the commanded pose clears the official inclusion margin; the settled
        # pose is allowed to rest on the floor plane
        self.assertTrue(
            agent.Geometry.inside_container(
                agent.AABB(tuple(commanded), candidate.size), container
            )
        )
        self.assertFalse(
            agent.Geometry.inside_container(candidate, container)
        )
        self.assertTrue(
            agent.Geometry.inside_container(
                candidate, container, floor_clearance=0.0
            )
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


class SoftFloorPlanTests(unittest.TestCase):
    """Task A's soft floor under the hard cargo (config.plan_soft_floor_under_count,
    reports/wedge/a-soft-floor.md): off by default, planned only under the
    count gate, the cover rule waived for the soft floor alone."""

    def _config(self, **over):
        import dataclasses

        from rule_alpha.config import DEFAULT_CONFIG

        return dataclasses.replace(DEFAULT_CONFIG, **over)

    @staticmethod
    def _box(index, x, y, l, w, h, soft=False, prio=False, z0=0.04):
        return {"index": index, "length": l, "width": w, "height": h, "mass": 8.0, "is_soft": soft,
                "is_prioritized": prio, "pos": (x, y, z0 + h / 2.0), "orn": (0.0, 0.0, 0.0, 1.0)}

    def _containers(self, packed=()):
        from bench.scenes import make_scene

        containers = make_scene(1, "c1", "A").rule_alpha_containers()
        containers[0]["packed_items"] += list(packed)
        return containers

    def test_flags_default_off(self):
        from rule_alpha.config import DEFAULT_CONFIG

        self.assertFalse(DEFAULT_CONFIG.plan_soft_floor_under_count)
        self.assertFalse(DEFAULT_CONFIG.plan_soft_floor_active)
        self.assertEqual(DEFAULT_CONFIG.plan_soft_floor_overrides, "")

    def test_cover_view_waives_the_soft_floor_alone(self):
        from rule_alpha import layer1
        from rule_alpha.geometry import AABB
        from rule_alpha.planner import _cover_view
        from wedge_rl.stack import covers_other_attribute

        cfg = self._config()
        soft = self._box(1, 0.0, 0.3, 0.6, 0.3, 0.25, soft=True)
        prio = self._box(2, 0.0, -0.3, 0.55, 0.4, 0.24, prio=True)
        containers = self._containers([soft, prio])
        board = layer1.Board(containers, cfg)
        model, container = board.model(0), board.container(0)
        over_soft = AABB((0.0, 0.3, 0.29 + 0.125), (0.65, 0.45, 0.25), "t")
        over_prio = AABB((0.0, -0.3, 0.28 + 0.125), (0.65, 0.45, 0.25), "t")
        self.assertTrue(covers_other_attribute(over_soft, container, False, False))
        self.assertFalse(covers_other_attribute(over_soft, _cover_view(container, model, True), False, False))
        self.assertTrue(covers_other_attribute(over_soft, _cover_view(container, model, False), False, False))
        # the priority cargo keeps its cover rule
        self.assertTrue(covers_other_attribute(over_prio, _cover_view(container, model, True), False, False))

    def test_soft_floor_group_is_one_level_band(self):
        from rule_alpha import classify as cls
        from rule_alpha.planner import _soft_floor_eligible, _soft_floor_group

        cfg = self._config()
        dims = [(0.60, 0.30, 0.25)] * 3 + [(0.65, 0.35, 0.23)] * 4 + [(0.45, 0.30, 0.20)] * 2 + [(0.50, 0.40, 0.40)]
        profiles = [cls.classify_item(i, {"index": i, "length": l, "width": w, "height": h, "mass": 5.0,
                                          "is_soft": True, "is_prioritized": i == 1}, cfg)
                    for i, (l, w, h) in enumerate(dims)]
        eligible = [p for p in profiles if _soft_floor_eligible(p, cfg)]
        # the 0.40 m box and the priority box stay out
        self.assertNotIn(9, [p.index for p in eligible])
        self.assertNotIn(1, [p.index for p in eligible])
        group = _soft_floor_group(eligible, cfg)
        self.assertEqual(sorted(p.index for p in group), [3, 4, 5, 6])   # the 0.23 m band, most footprint
        wide = _soft_floor_group(eligible, self._config(plan_soft_floor_level_tolerance=0.03))
        self.assertEqual(sorted(p.index for p in wide), [0, 2, 3, 4, 5, 6])

    def test_variant_respects_the_gate(self):
        from unittest import mock

        from rule_alpha import planner

        agent = mock.Mock()
        agent.config = self._config(plan_soft_floor_under_count=True, plan_value_margin=2)
        agent._count_threshold.return_value = 10
        plan = [{"index": i} for i in range(12)]
        with mock.patch.object(planner, "_plan_once") as once:
            order, out = planner._soft_floor_variant(agent, [], time.perf_counter() + 10,
                                                     ("x", 0, None, None, None, None), [1], plan)
            once.assert_not_called()
        self.assertIs(out, plan)
        agent._count_threshold.return_value = None
        with mock.patch.object(planner, "_plan_once") as once:
            planner._soft_floor_variant(agent, [], time.perf_counter() + 10,
                                        ("x", 0, None, None, None, None), [1], plan[:3])
            once.assert_not_called()

    def test_variant_plays_when_it_holds_more_and_marks_the_poses(self):
        from unittest import mock

        from rule_alpha import planner, stability

        agent = mock.Mock()
        agent.board.models = []
        agent.config = self._config(plan_soft_floor_under_count=True, plan_value_margin=2,
                                    plan_soft_floor_needs_gate=False,
                                    plan_soft_floor_overrides="reserve_headroom_for_soft=false")
        agent._count_threshold.return_value = 10
        seen = {}
        floor = {"index": 1, "container_idx": 0, "center": [0.0, 0.3, 0.165], "size": [0.6, 0.3, 0.25],
                 "bottom": 0.04, "soft_floor": True}
        hard = {"index": 2, "container_idx": 0, "center": [0.0, 0.3, 0.415], "size": [0.65, 0.45, 0.25],
                "bottom": 0.29}
        beside = {"index": 3, "container_idx": 0, "center": [0.0, -0.4, 0.165], "size": [0.65, 0.45, 0.25],
                  "bottom": 0.04}

        def fake_once(a, items, deadline, name, log, layout_index=0):
            seen["active"] = a.config.plan_soft_floor_active
            seen["reserve"] = a.config.reserve_headroom_for_soft
            seen["share"] = stability.SOFT_STRUCTURE_FLOOR_SHARE
            return [1, 2, 3], [floor, hard, beside]

        share = stability.SOFT_STRUCTURE_FLOOR_SHARE
        with mock.patch.object(planner, "_plan_once", side_effect=fake_once):
            order, out = planner._soft_floor_variant(agent, [], time.perf_counter() + 10,
                                                     ("x", 0, None, None, None, None), [9], [{"index": 9}])
        self.assertEqual(seen, {"active": True, "reserve": False, "share": 0.0})
        self.assertEqual(stability.SOFT_STRUCTURE_FLOOR_SHARE, share)   # restored
        self.assertFalse(agent.config.plan_soft_floor_active)           # restored
        self.assertEqual(order, [1, 2, 3])
        self.assertTrue(hard.get("over_soft"))
        self.assertAlmostEqual(hard["replay_drop"], agent.config.plan_soft_floor_replay_drop)
        self.assertFalse(beside.get("over_soft", False))
        # fewer items than the plan: the plan stays
        with mock.patch.object(planner, "_plan_once", side_effect=fake_once):
            order, out = planner._soft_floor_variant(agent, [], time.perf_counter() + 10,
                                                     ("x", 0, None, None, None, None), [9],
                                                     [{"index": i} for i in range(5)])
        self.assertEqual(order, [9])
        # with the gate rule (the default) a soft-floor plan under the
        # threshold plus the margin does not play however many it holds
        import dataclasses

        agent.config = dataclasses.replace(agent.config, plan_soft_floor_needs_gate=True)
        with mock.patch.object(planner, "_plan_once", side_effect=fake_once):
            order, out = planner._soft_floor_variant(agent, [], time.perf_counter() + 10,
                                                     ("x", 0, None, None, None, None), [9], [{"index": 9}])
        self.assertEqual(order, [9])
        agent._count_threshold.return_value = 1
        with mock.patch.object(planner, "_plan_once", side_effect=fake_once):
            order, out = planner._soft_floor_variant(agent, [], time.perf_counter() + 10,
                                                     ("x", 0, None, None, None, None), [9], [{"index": 9}])
        self.assertEqual(order, [1, 2, 3])   # 3 items hold 1 + 2

    def test_online_view_and_the_dry_run_rule(self):
        from rule_alpha.planner import soft_floor_board_view, soft_floor_yields

        soft = self._box(1, 0.0, 0.3, 0.6, 0.3, 0.25, soft=True)
        other = self._box(5, 0.5, -0.3, 0.6, 0.3, 0.25, soft=True)
        containers = self._containers([soft, other])
        agent = type("A", (), {})()
        agent.config = self._config()
        agent.plan_source = "planner"
        agent.plan_by_index = {1: {"index": 1, "soft_floor": True}, 2: {"index": 2}}
        view = soft_floor_board_view(agent, containers)
        packed = {p["index"]: p for p in view[0]["packed_items"]}
        self.assertFalse(packed[1]["is_soft"])
        self.assertTrue(packed[5]["is_soft"])
        self.assertTrue(containers[0]["packed_items"][-2]["is_soft"])   # the observation untouched
        agent.config = self._config(plan_soft_floor_online=False)
        self.assertIs(soft_floor_board_view(agent, containers), containers)
        agent.config = self._config()
        agent.plan_source = "dry-run"
        self.assertIs(soft_floor_board_view(agent, containers), containers)
        plan = [{"index": 1, "soft_floor": True}, {"index": 2}]
        agent._count_threshold = lambda: 3
        self.assertTrue(soft_floor_yields(agent, plan, [{}, {}, {}]))
        agent._count_threshold = lambda: 2   # the soft-floor plan holds the count: the score decides
        self.assertFalse(soft_floor_yields(agent, plan, [{}, {}, {}]))
        agent._count_threshold = lambda: None
        self.assertFalse(soft_floor_yields(agent, plan, [{}, {}]))
        self.assertFalse(soft_floor_yields(agent, [{"index": 2}], [{}, {}, {}]))

    def test_replay_accepts_a_hard_pose_over_the_soft_floor_only_when_marked(self):
        from rule_alpha import classify as cls
        from rule_alpha import layer1, stability
        from rule_alpha.planner import replay

        cfg = self._config(no_cover_other_attribute=True, soft_is_structure=True, plan_replay_drop=0.0)
        # the soft box settled 1.2 cm into the floor, as in the probe
        soft = self._box(1, 0.0, 0.3, 0.6, 0.3, 0.25, soft=True, z0=0.028)
        containers = self._containers([soft])
        board = layer1.Board(containers, cfg)
        item = {"index": 2, "length": 0.65, "width": 0.45, "height": 0.25, "mass": 13.0,
                "is_soft": False, "is_prioritized": False}
        profile = cls.classify_item(2, item, cfg)
        o = next(o for o in profile.orientations if abs(o.dz - 0.25) < 1e-9 and abs(o.dx - 0.65) < 1e-9)
        entry = {"index": 2, "step": 2, "container_idx": 0, "orientation": o.index,
                 "center": [0.0, 0.3, 0.29 + 0.125], "size": [o.dx, o.dy, o.dz], "on_floor": False}
        agent = mock_agent = type("A", (), {})()
        mock_agent.config = cfg
        mock_agent.plan_misses = 0
        saved = (stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE)
        try:
            stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE = 0.7, 0.35
            self.assertIsNone(replay(agent, board, [(0, profile)], {2: dict(entry)}))
            marked = dict(entry, over_soft=True, replay_drop=0.06)
            hit = replay(agent, board, [(0, profile)], {2: marked})
            self.assertIsNotNone(hit)
            box = hit[1].placement.box
            # at the planned height (within plan_soft_floor_contact_tolerance
            # of the settled top) or at the settled top
            self.assertTrue(0.277 <= float(box.minimum[2]) <= 0.291, float(box.minimum[2]))
            self.assertEqual((stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE), (0.7, 0.35))
        finally:
            stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE = saved


def _column(index, x, y, w=0.1, d=0.5, h=0.5, z0=0.04):
    return {"index": index, "length": w, "width": d, "height": h, "mass": 10.0, "is_soft": False,
            "is_prioritized": False, "pos": (x, y, z0 + h / 2.0), "orn": (0.0, 0.0, 0.0, 1.0)}


class BridgeRescueFlagTests(unittest.TestCase):
    """rule_alpha's declining-call flags (reports/wedge/bridge-rescue.md):
    the grid rescue's contact filter (config.grid_rescue_min_support) and
    the low phase's rescue reserve (config.low_phase_rescue_seconds)."""

    ITEM = {"index": 9, "length": 0.6, "width": 0.4, "height": 0.2, "mass": 5.0,
            "is_soft": False, "is_prioritized": False}

    def _config(self, **over):
        import dataclasses

        from rule_alpha.config import DEFAULT_CONFIG

        return dataclasses.replace(DEFAULT_CONFIG, **over)

    def _containers(self, columns=True):
        from bench.scenes import make_scene

        containers = make_scene(1, "c1", "C").rule_alpha_containers()
        if columns:
            # two 0.1 m columns 0.5 m tall with a 0.3 m slot between them:
            # a 0.6 m box across them rests on a third of its footprint
            containers[0]["packed_items"] += [_column(1, 0.35, 0.4), _column(2, 0.75, 0.4)]
        return containers

    # -- the contact filter ---------------------------------------------------
    def test_grid_min_support_default_keeps_the_old_figures(self):
        from rule_alpha.agent import RuleAlphaAgent

        a = RuleAlphaAgent(config=self._config())
        self.assertEqual(a._grid_min_support(False), 0.5)
        self.assertEqual(a._grid_min_support(True), 0.5)
        a = RuleAlphaAgent(config=self._config(count_mode_min_support=0.25))
        self.assertEqual(a._grid_min_support(False), 0.5)
        self.assertEqual(a._grid_min_support(True), 0.25)

    def test_grid_min_support_honours_the_flag(self):
        from rule_alpha.agent import RuleAlphaAgent

        a = RuleAlphaAgent(config=self._config(grid_rescue_min_support=0.25))
        self.assertEqual(a._grid_min_support(False), 0.25)
        self.assertEqual(a._grid_min_support(True), 0.25)
        a = RuleAlphaAgent(config=self._config(grid_rescue_min_support=0.3, count_mode_min_support=0.25))
        self.assertEqual(a._grid_min_support(False), 0.3)
        self.assertEqual(a._grid_min_support(True), 0.25)  # the smaller on the count path

    def _grid_poses_on_the_columns(self, **over):
        """(validated, accepted) grid-rescue poses resting on the columns'
        tops, the shadow stubbed out (every check fails)."""
        from unittest import mock

        from rule_alpha import classify as cls
        from rule_alpha import layer1
        from rule_alpha.agent import RuleAlphaAgent

        cfg = self._config(grid_rescue=0.05, no_cover_other_attribute=True, conservative_transport=False, **over)
        containers = self._containers()
        a = RuleAlphaAgent(config=cfg)
        a.board = layer1.Board(containers, cfg)
        pool = [dict(self.ITEM)]
        ordered = layer1.pool_order([(0, cls.classify_item(9, self.ITEM, cfg))], cfg)
        a._shadow_synced = True
        a._shadow_observation = {"container_list": containers}
        seen = []
        real = layer1.validate

        def record(box, model, container, c):
            ok, why = real(box, model, container, c)
            seen.append((float(box.center[2]) - float(box.size[2]) / 2.0, ok))
            return ok, why

        with mock.patch.object(layer1, "validate", side_effect=record), \
                mock.patch.object(a, "_shadow_sim", return_value=object()), \
                mock.patch.object(a, "_shadow_verdict", return_value={}), \
                mock.patch.object(a, "_shadow_hard", return_value=True):
            self.assertIsNone(a._grid_rescue(ordered, pool, float("inf"), count=False, own_window=False))
        high = [ok for bottom, ok in seen if bottom > 0.5]
        return len(high), sum(1 for ok in high if ok)

    def test_grid_rescue_default_filter_refuses_the_bridge(self):
        _validated, accepted = self._grid_poses_on_the_columns()
        self.assertEqual(accepted, 0)

    def test_grid_rescue_lower_filter_admits_the_bridge(self):
        validated0, _ = self._grid_poses_on_the_columns()
        validated, accepted = self._grid_poses_on_the_columns(grid_rescue_min_support=0.25)
        self.assertGreater(validated, validated0)
        self.assertGreater(accepted, 0)  # the validator's convex hull accepts the bridges

    # -- the low phase's rescue reserve ---------------------------------------
    def _deadlines(self, low: bool, pool_size: int = 1, **over):
        """The deadlines one declining call hands its stages (relative to
        the call's start): the stack option's, the last resort's, the
        physics resort's and the grid rescue's."""
        from unittest import mock

        from rule_alpha import layer1
        from rule_alpha.agent import RuleAlphaAgent

        got = {}

        class Option:
            headroom_reserve = 0.0

            def propose(self, board, profile, deadline=None):
                got["stack"] = deadline
                return None

        cfg = self._config(phase_switch=True, phase_switch_resort_first=False, shadow_check=True,
                           physics_resort=True, grid_rescue=0.05, last_resort_relax=True,
                           policy_budget_seconds=4.5, **over)
        a = RuleAlphaAgent(config=cfg, stack_option=Option())

        def last_resort(containers, ordered, deadline=float("inf")):
            got["last_resort"] = deadline
            return None

        def resort(ordered, pool, deadline, count=False):
            got["resort"] = deadline
            return None

        def grid(ordered, pool, deadline, count=False, own_window=True):
            got["grid"] = deadline
            return None

        observation = {"container_list": self._containers(columns=False),
                       "pool_list": [dict(self.ITEM, index=9 + k) for k in range(pool_size)]}
        with mock.patch.object(layer1, "choose_for_item", return_value=None), \
                mock.patch.object(a, "_low_phase", return_value=low), \
                mock.patch.object(a, "_last_resort", side_effect=last_resort), \
                mock.patch.object(a, "_can_start", return_value=True), \
                mock.patch.object(a, "_physics_resort", side_effect=resort), \
                mock.patch.object(a, "_grid_rescue", side_effect=grid):
            self.assertIsNone(a.policy(observation))
        started = a._policy_started
        return {k: (None if v is None else v - started) for k, v in got.items()}, a

    def test_low_phase_reserve_off_by_default(self):
        for low in (False, True):
            d, a = self._deadlines(low)
            self.assertIsNone(d["stack"])  # no stack_deadline
            self.assertFalse(a._low_cut)
            self.assertAlmostEqual(d["resort"], d["grid"], places=6)  # the resort's whole window

    def test_low_phase_reserve_untouched_outside_the_low_phase(self):
        base, _ = self._deadlines(False, stack_deadline=True)
        d, a = self._deadlines(False, stack_deadline=True, low_phase_rescue_seconds=1.5)
        self.assertFalse(a._low_cut)
        self.assertAlmostEqual(d["stack"], 0.85 * 4.5, places=6)
        self.assertAlmostEqual(d["stack"], base["stack"], places=6)
        self.assertAlmostEqual(d["resort"], d["grid"], places=6)
        self.assertAlmostEqual(d["last_resort"], base["last_resort"], delta=0.05)

    def test_low_phase_reserve_shortens_the_stages_in_the_low_phase(self):
        base, _ = self._deadlines(True)
        d, a = self._deadlines(True, low_phase_rescue_seconds=1.5)
        self.assertTrue(a._low_cut)
        # the stack option's generation stops at its share of the budget less the reserve
        self.assertAlmostEqual(d["stack"], 0.85 * (4.5 - 1.5), places=6)
        self.assertLessEqual(d["last_resort"], 4.5 - 1.5 + 1e-6)
        # the resort hands the reserve to the grid rescue; the end is unchanged
        self.assertAlmostEqual(d["grid"], base["grid"], places=2)
        self.assertAlmostEqual(d["grid"] - d["resort"], 1.5, places=6)

    def test_low_phase_reserve_single_gate(self):
        # a pool of one (Task C): the gate lets the reserve act
        _d, a = self._deadlines(True, low_phase_rescue_seconds=1.5, low_phase_rescue_single=True)
        self.assertTrue(a._low_cut)
        # a pool of several (Task B): the gate keeps it off
        _d, a = self._deadlines(True, pool_size=3, low_phase_rescue_seconds=1.5, low_phase_rescue_single=True)
        self.assertFalse(a._low_cut)
        _d, a = self._deadlines(True, pool_size=3, low_phase_rescue_seconds=1.5)
        self.assertTrue(a._low_cut)


if __name__ == "__main__":
    unittest.main()
