"""Regression tests for the rule-alpha Layer 1 prototype.

These lock down the things that would silently produce a wrong-looking board:
the derived ULD geometry, the floor-lift convention, the orientation policies,
the slope gate and the hole diagnostics.  They must stay fast — the scenario
sweep lives in ``rule_alpha.runner``, not here.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.diagnostics import (  # noqa: E402
    FloorGrid,
    connected_components,
    hole_report,
    largest_rectangle_in_mask,
)
from rule_alpha.geometry import (  # noqa: E402
    ContainerModel,
    Rect,
    cut_corner_planes,
    make_container_dict,
)

ULD = dict(length=2.0, width=1.45, height=1.61, thickness=0.04, cut_x=0.44, cut_y=0.40)


def _model(**overrides):
    spec = dict(ULD)
    spec.update(overrides)
    container = make_container_dict(index=0, **spec)
    return container, ContainerModel(container, DEFAULT_CONFIG)


class DerivedGeometryTest(unittest.TestCase):
    def test_planes_match_the_simulator_mesh(self):
        """The analytic cross section must equal the simulator's own planes."""
        simulator_src = REPO_ROOT / "simulator" / "src"
        if str(simulator_src) not in sys.path:
            sys.path.insert(0, str(simulator_src))
        try:
            from ground_handling.utils import aff, write_open_cut_corner_cup_obj
        except ImportError:  # pragma: no cover - simulator extras absent
            self.skipTest("simulator sources unavailable")

        points, normals = cut_corner_planes(**ULD, buffer=0.0)
        with tempfile.TemporaryDirectory() as directory:
            reference_points, reference_normals = write_open_cut_corner_cup_obj(
                os.path.join(directory, "uld.obj"),
                width=ULD["length"], height=ULD["height"],
                cut_x=ULD["cut_x"], cut_y=ULD["cut_y"], depth=ULD["width"],
                wall=ULD["thickness"], bottom=ULD["thickness"],
            )
        rotation = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
        expected_points = np.asarray(
            aff(reference_points, rotation, (0.0, 0.0, ULD["height"] / 2.0))
        )
        expected_normals = np.asarray(aff(reference_normals, rotation, (0, 0, 0)))
        np.testing.assert_allclose(np.asarray(points), expected_points, atol=1e-9)
        np.testing.assert_allclose(np.asarray(normals), expected_normals, atol=1e-9)

    def test_chamfer_is_a_bottom_edge_bevel_not_a_top_corner(self):
        _container, model = _model()
        self.assertAlmostEqual(model.z_floor, 0.04, places=6)
        self.assertLess(model.x_floor_min, model.x_wall_max)
        # at the floor the usable x starts well right of the wall
        self.assertGreater(model.x_floor_min - model.x_wall_min, 0.30)
        # and the restriction disappears above the chamfer top
        self.assertAlmostEqual(
            model.x_limit_at_height(model.z_chamfer_top + 0.05),
            model.x_wall_min, places=6,
        )
        self.assertGreater(model.z_chamfer_top, model.z_floor)

    def test_floor_limit_is_independent_of_item_height(self):
        """The binding corner is the bottom one, so a tall box gains nothing."""
        _container, model = _model()
        for height in (0.10, 0.40, 0.90):
            box = AABB(
                center=(model.x_floor_min + 0.30, 0.0, model.z_floor + height / 2.0),
                size=(0.60, 0.40, height), name="probe",
            )
            self.assertTrue(model.inside(box, 0.0, floor_clearance=0.0))
            shifted = AABB(
                center=(model.x_floor_min - 0.05, 0.0, model.z_floor + height / 2.0),
                size=(0.60, 0.40, height), name="probe",
            )
            self.assertFalse(model.inside(shifted, 0.0, floor_clearance=0.0))


class FloorLiftTest(unittest.TestCase):
    def test_settled_floor_pose_would_fail_the_official_margin(self):
        """Documents why placements are commanded above the floor."""
        container, model = _model()
        settled = AABB((0.3, 0.2, model.z_floor + 0.12), (0.6, 0.4, 0.24), "settled")
        # official check_inclusion demands dots <= -0.005
        self.assertFalse(model.inside(settled, 0.005))
        self.assertTrue(model.inside(settled, 0.005, floor_clearance=0.0))

        commanded = layer1.action_center(settled, model, container, DEFAULT_CONFIG)
        lifted = AABB(tuple(commanded), settled.size, "commanded")
        self.assertTrue(lifted.center[2] > settled.center[2])
        self.assertTrue(model.inside(lifted, DEFAULT_CONFIG.inclusion_clearance))

    def test_the_floor_lift_is_never_applied_twice(self):
        """rule-alpha delegates the release height to the shared helper.

        Both modules know about release-and-drop, so both would happily add a
        lift.  Two lifts put the commanded pose 4 cm up while the transport
        sweep — which is derived from the shared helper — still modelled 2 cm,
        and tall wall-front cargo ended up inside the small shelf's safety
        margin.
        """
        from rule_alpha._reuse import simulator_action_center

        container, model = _model()
        dz = 0.24
        settled = AABB((0.3, 0.2, model.z_floor + dz / 2.0), (0.6, 0.4, dz), "settled")

        shared = float(simulator_action_center(settled, container)[2])
        commanded = float(
            layer1.action_center(settled, model, container, DEFAULT_CONFIG)[2]
        )
        settled_z = float(settled.center[2])

        # exactly one lift, and it is the shared helper's when it applies one
        self.assertGreater(commanded, settled_z)
        self.assertAlmostEqual(commanded, shared, places=9)
        self.assertLessEqual(
            commanded - settled_z, DEFAULT_CONFIG.floor_action_lift + 1e-9
        )

    def test_a_shelf_placement_keeps_only_the_shelf_lift(self):
        from rule_alpha._reuse import simulator_action_center

        container, model = _model()
        shelf = model.small_shelf
        dz = 0.30
        settled = AABB(
            (float(shelf.center[0]), 0.0, float(shelf.maximum[2]) + dz / 2.0),
            (0.2, 0.4, dz), "settled",
        )
        shared = float(simulator_action_center(settled, container)[2])
        commanded = float(
            layer1.action_center(settled, model, container, DEFAULT_CONFIG)[2]
        )
        self.assertAlmostEqual(commanded, shared, places=9)
        self.assertGreater(commanded, float(settled.center[2]))

    def test_lift_stays_inside_the_validator_direct_rest_window(self):
        # above 0.05 m the validator stops treating it as a direct rest and
        # flies the item in from 8 cm up instead
        self.assertLess(DEFAULT_CONFIG.floor_action_lift, 0.05)
        self.assertGreater(DEFAULT_CONFIG.floor_action_lift, 0.005)


class SlopeGateTest(unittest.TestCase):
    def test_a_mere_overhang_is_not_slope_infill(self):
        _container, model = _model()
        box = AABB(
            center=(model.x_floor_min - 0.004 + 0.35, 0.0, 0.30),
            size=(0.70, 0.30, 0.20), name="overhang",
        )
        self.assertLess(float(box.minimum[0]), model.x_floor_min)
        self.assertFalse(layer1.in_slope_pocket(box, model, DEFAULT_CONFIG))

    def test_a_real_pocket_box_is_slope_infill(self):
        _container, model = _model()
        width = 0.26
        centre_x = model.x_floor_min - width / 2.0 - 0.01
        box = AABB((centre_x, 0.0, 0.34), (width, 0.30, 0.16), "pocket")
        self.assertTrue(layer1.in_slope_pocket(box, model, DEFAULT_CONFIG))

    def test_no_floor_resting_box_can_reach_the_pocket(self):
        """The negative finding the README states: the wedge is unreachable
        from the floor, whatever the box size."""
        container, model = _model()
        for dx in (0.10, 0.20, 0.30, 0.45):
            for dz in (0.15, 0.30, 0.55):
                centre_x = model.x_floor_min - dx / 2.0
                box = AABB(
                    (centre_x, 0.0, model.z_floor + dz / 2.0),
                    (dx, 0.30, dz), "floor-pocket",
                )
                self.assertTrue(layer1.in_slope_pocket(box, model, DEFAULT_CONFIG))
                valid, _why = layer1.validate(box, model, container, DEFAULT_CONFIG)
                self.assertFalse(
                    valid, f"a floor box of {dx}x{dz} must not fit the pocket"
                )

    def test_bevel_is_too_steep_to_rest_on(self):
        _container, model = _model()
        run = model.x_floor_min - model.x_wall_min
        rise = model.z_chamfer_top - model.z_floor
        self.assertGreater(rise / run, 0.8, "friction is 0.8; a shallower bevel "
                                            "would change the conclusion")


class ClassificationTest(unittest.TestCase):
    def _profile(self, length, width, height, **flags):
        item = {
            "index": 0, "length": length, "width": width, "height": height,
            "mass": 8.0, "is_soft": flags.get("soft", False),
            "is_prioritized": flags.get("priority", False),
        }
        return cls.classify_item(0, item, DEFAULT_CONFIG)

    def test_four_cargo_classes(self):
        self.assertEqual(self._profile(0.6, 0.4, 0.3).cargo_class, cls.NORMAL_HARD)
        self.assertEqual(self._profile(0.6, 0.4, 0.3, soft=True).cargo_class, cls.SOFT)
        self.assertEqual(
            self._profile(0.6, 0.4, 0.3, priority=True).cargo_class, cls.PRIORITY
        )
        self.assertEqual(
            self._profile(0.6, 0.4, 0.3, soft=True, priority=True).cargo_class,
            cls.SOFT_PRIORITY,
        )

    def test_elongation_uses_max_over_median(self):
        profile = self._profile(1.20, 0.30, 0.20)
        self.assertAlmostEqual(profile.elongation, 1.20 / 0.30, places=6)
        self.assertTrue(profile.is_elongated)
        self.assertFalse(self._profile(0.60, 0.45, 0.30).is_elongated)

    def test_tipping_bands_follow_the_spec(self):
        bands = [
            ((0.6, 0.5, 0.5), cls.TIP_NORMAL),
            ((0.6, 0.4, 0.7), cls.TIP_WALL_PREFERRED),
            ((0.6, 0.3, 0.7), cls.TIP_WALL_STRONG),
            ((0.6, 0.2, 0.8), cls.TIP_NEEDS_BACKING),
        ]
        for (dx, dy, dz), expected in bands:
            orientation = cls.Orientation(0, dx, dy, dz)
            self.assertEqual(orientation.tipping_band(DEFAULT_CONFIG), expected,
                             f"{dx}x{dy}x{dz} -> R={orientation.tipping_ratio:.2f}")

    def test_floor_policy_maximises_footprint_shelf_policy_minimises_it(self):
        profile = self._profile(0.70, 0.50, 0.25)
        floor_first = cls.floor_orientation_order(profile, DEFAULT_CONFIG)[0]
        shelf_first = cls.shelf_orientation_order(profile, DEFAULT_CONFIG)[0]
        self.assertAlmostEqual(floor_first.footprint, 0.70 * 0.50, places=6)
        self.assertLess(shelf_first.footprint, floor_first.footprint)
        self.assertLessEqual(
            shelf_first.tipping_ratio, DEFAULT_CONFIG.max_shelf_tipping_ratio
        )

    def test_structural_policy_buys_height(self):
        profile = self._profile(1.10, 0.28, 0.20)
        first = cls.structural_orientation_order(profile, DEFAULT_CONFIG)[0]
        self.assertAlmostEqual(first.dz, 1.10, places=6)

    def test_a_long_soft_bag_still_lies_flat(self):
        profile = self._profile(1.10, 0.28, 0.20, soft=True)
        self.assertTrue(profile.is_elongated)
        chosen = cls.orientation_order(
            profile, "floor", cls.ROLE_ELONGATED, DEFAULT_CONFIG
        )[0]
        self.assertAlmostEqual(chosen.footprint, 1.10 * 0.28, places=6)


class DiagnosticsTest(unittest.TestCase):
    def test_largest_rectangle(self):
        mask = np.array(
            [
                [1, 1, 1, 0],
                [1, 1, 1, 0],
                [1, 1, 1, 1],
            ],
            dtype=bool,
        )
        area, _box = largest_rectangle_in_mask(mask)
        self.assertEqual(area, 9)

    def test_connected_components_counts_islands(self):
        mask = np.zeros((6, 6), dtype=bool)
        mask[0:2, 0:2] = True
        mask[4:6, 4:6] = True
        _labels, count = connected_components(mask)
        self.assertEqual(count, 2)

    def test_reachable_from_boundary_finds_enclosed_cells(self):
        usable = np.ones((7, 7), dtype=bool)
        free = np.ones((7, 7), dtype=bool)
        free[2:5, 2:5] = True
        # ring of occupied cells around the middle cell
        free[3, 3] = True
        free[2:5, 2] = False
        free[2:5, 4] = False
        free[2, 2:5] = False
        free[4, 2:5] = False
        reached = layer1.reachable_from_boundary(free, usable)
        self.assertFalse(bool(reached[3, 3]), "the enclosed cell must not be reached")
        self.assertTrue(bool(reached[0, 0]))

    def test_interior_hole_is_separated_from_open_free_space(self):
        _container, model = _model()
        grid = FloorGrid(model, 0.04)
        # a closed ring of support around a small courtyard
        courtyard = Rect(-0.05, 0.20, -0.05, 0.20)
        ring_outer = Rect(-0.30, 0.45, -0.30, 0.45)
        grid.stamp(Rect(ring_outer.x_min, ring_outer.x_max,
                        ring_outer.y_min, courtyard.y_min), 0.3, 1, False)
        grid.stamp(Rect(ring_outer.x_min, ring_outer.x_max,
                        courtyard.y_max, ring_outer.y_max), 0.3, 1, False)
        grid.stamp(Rect(ring_outer.x_min, courtyard.x_min,
                        courtyard.y_min, courtyard.y_max), 0.3, 1, False)
        grid.stamp(Rect(courtyard.x_max, ring_outer.x_max,
                        courtyard.y_min, courtyard.y_max), 0.3, 1, False)

        report = hole_report(grid, DEFAULT_CONFIG)
        self.assertEqual(report["interior_hole_count"], 1)
        hole = report["largest_interior_hole"]
        self.assertGreater(hole["area"], 0.03)
        self.assertGreater(hole["surrounding_support_height"], 0.2)
        self.assertIn("hard", hole["surrounding_support_types"])
        # the rest of the floor is still open, and much bigger
        self.assertGreater(report["largest_open_free_area"], hole["area"])


class VolumeReportTest(unittest.TestCase):
    def test_usable_volume_matches_the_simulator_formula(self):
        """The denominator must be the one the official evaluator divides by."""
        from rule_alpha.geometry import simulator_container_volume

        for shelf in (False, True):
            container = make_container_dict(index=0, require_shelf=shelf, **ULD)
            model = ContainerModel(container, DEFAULT_CONFIG)
            expected = simulator_container_volume(
                ULD["length"], ULD["width"], ULD["height"], ULD["thickness"],
                ULD["cut_x"], ULD["cut_y"], 0.0, shelf,
            )
            self.assertAlmostEqual(model.usable_volume, expected, places=9)
            self.assertAlmostEqual(model.usable_volume, container["volume"], places=9)

    def test_observation_volume_wins_over_the_recomputed_one(self):
        container = make_container_dict(index=0, **ULD)
        container["volume"] = 3.5
        model = ContainerModel(container, DEFAULT_CONFIG)
        self.assertAlmostEqual(model.usable_volume, 3.5)

    def test_volume_report_is_internally_consistent(self):
        from rule_alpha.diagnostics import volume_report
        from rule_alpha.episode import run_episode
        from rule_alpha.scenarios import Scenario, _normal_container, _stream

        scenario = Scenario(
            name="volume-test", description="",
            containers=[_normal_container(shelf=True)],
            items=_stream(77, 14, soft_ratio=0.3),
        )
        result = run_episode(scenario, DEFAULT_CONFIG, snapshot_steps=0)
        board = result.board
        placements = board.placements[0]
        report = volume_report(board.model(0), placements, DEFAULT_CONFIG)

        self.assertGreater(report["placed_volume_m3"], 0.0)
        # each field is rounded to 5 dp independently, so the split can differ
        # from the total by a rounding step
        self.assertAlmostEqual(
            report["placed_volume_m3"],
            report["placed_volume_floor_m3"] + report["placed_volume_shelf_m3"],
            places=4,
        )
        self.assertAlmostEqual(
            report["volume_fill_ratio"],
            round(
                report["placed_volume_m3"]
                / report["usable_container_volume_m3"], 4,
            ),
            places=4,
        )
        # structural cargo counts towards occupied volume, unlike flatness
        self.assertLessEqual(
            report["structural_volume_m3"], report["placed_volume_m3"]
        )
        # one layer cannot fill a 1.6 m container
        self.assertLess(report["volume_fill_ratio"], 0.5)

    def test_structural_and_shelf_cargo_stay_out_of_the_foundation_slab(self):
        """The slab ratio uses the same mask as the flatness metric.

        A shelf item sits at ~1.3 m and a wall-front piece is deliberately
        tall; letting either set the envelope height would divide the normal
        foundation by floor it never covered.
        """
        from rule_alpha.diagnostics import volume_report
        from rule_alpha.episode import run_episode
        from rule_alpha.scenarios import Scenario, _normal_container, _stream

        scenario = Scenario(
            name="slab-mask", description="",
            containers=[_normal_container(shelf=True)],
            items=_stream(91, 16, soft_ratio=0.5),
        )
        result = run_episode(scenario, DEFAULT_CONFIG, snapshot_steps=0)
        board = result.board
        placements = board.placements[0]
        excluded = [
            p for p in placements
            if p.surface == "shelf" or p.is_structural
        ]
        foundation = [
            p for p in placements
            if p.surface != "shelf" and not p.is_structural
        ]
        if not excluded or not foundation:
            self.skipTest("scenario produced no mixed board")

        model = board.model(0)
        report = volume_report(model, placements, DEFAULT_CONFIG)

        foundation_height = max(p.top_z for p in foundation) - model.z_floor
        self.assertAlmostEqual(
            report["foundation_slab_height_m"],
            round(foundation_height, 4),
            places=3,
        )
        self.assertAlmostEqual(
            report["foundation_volume_m3"],
            round(sum(p.volume for p in foundation), 5),
            places=4,
        )
        # the excluded cargo is not lost: it still counts in the total
        self.assertGreater(
            report["placed_volume_m3"], report["foundation_volume_m3"]
        )
        self.assertLessEqual(report["foundation_slab_fill_ratio"], 1.0)

    def test_a_lone_tall_structural_piece_does_not_flatten_the_slab_ratio(self):
        """The regression this rename exists for."""
        from rule_alpha.diagnostics import volume_report
        from rule_alpha import classify as cls, layer1
        from rule_alpha._reuse import AABB
        from rule_alpha.scenarios import _normal_container

        container = _normal_container()
        board = layer1.Board([container], DEFAULT_CONFIG)
        model = board.model(0)

        def placement(index, dims, centre, role):
            item = {
                "index": index, "length": dims[0], "width": dims[1],
                "height": dims[2], "mass": 8.0,
                "is_soft": False, "is_prioritized": False,
            }
            profile = cls.classify_item(index, item, DEFAULT_CONFIG)
            return layer1.Placement(
                profile=profile,
                orientation=cls.Orientation(0, *dims),
                container_idx=0,
                box=AABB(centre, dims, "settled"),
                surface="floor", surface_name="floor",
                role=role, archetype="test", reason="test",
            )

        flat = [
            placement(0, (0.6, 0.4, 0.2), (0.2, 0.2, model.z_floor + 0.1),
                      cls.ROLE_NONE),
            placement(1, (0.6, 0.4, 0.2), (0.85, 0.2, model.z_floor + 0.1),
                      cls.ROLE_NONE),
        ]
        spike = placement(
            2, (0.3, 0.3, 1.0), (-0.4, 0.2, model.z_floor + 0.5),
            cls.ROLE_WALL_FRONT,
        )

        without = volume_report(model, flat, DEFAULT_CONFIG)
        with_spike = volume_report(model, flat + [spike], DEFAULT_CONFIG)

        # the 1 m spike must not move the slab height or its ratio
        self.assertAlmostEqual(
            with_spike["foundation_slab_height_m"],
            without["foundation_slab_height_m"],
        )
        self.assertAlmostEqual(
            with_spike["foundation_slab_fill_ratio"],
            without["foundation_slab_fill_ratio"],
        )
        # but its volume is still counted in the total, and called out
        self.assertGreater(
            with_spike["volume_fill_ratio"], without["volume_fill_ratio"]
        )
        self.assertAlmostEqual(with_spike["structural_volume_m3"], 0.09, places=5)
        self.assertAlmostEqual(without["structural_volume_m3"], 0.0)


class WedgeStaircaseTest(unittest.TestCase):
    """RAW -> STAIRCASE -> SOFT_READY -> CLOSED around the chamfer wedge."""

    def _profiles(self, spec):
        out = []
        for index, (dims, flags) in enumerate(spec):
            item = {
                "index": index, "length": dims[0], "width": dims[1],
                "height": dims[2], "mass": 8.0,
                "is_soft": flags.get("soft", False),
                "is_prioritized": flags.get("priority", False),
            }
            out.append(cls.classify_item(index, item, DEFAULT_CONFIG))
        return out

    def test_the_first_step_cannot_overhang_but_the_second_can(self):
        """At floor height the chamfer limit *is* the floor limit."""
        from rule_alpha import triangle as tri

        _container, model = _model()
        at_floor = tri.max_overhang(
            model, model.x_floor_min, model.z_floor, 0.40, DEFAULT_CONFIG
        )
        self.assertAlmostEqual(at_floor, 0.0, places=6)

        higher = tri.max_overhang(
            model, model.x_floor_min, model.z_floor + 0.20, 0.40, DEFAULT_CONFIG
        )
        self.assertGreater(higher, 0.05)

    def test_stability_binds_before_the_chamfer_does(self):
        """Which is what lets the staircase keep climbing past the chamfer top
        instead of stalling there."""
        from rule_alpha import triangle as tri

        _container, model = _model()
        width = 0.40
        bottom = model.z_floor + 0.20
        geometric = model.x_floor_min - model.x_limit_at_height(bottom)
        allowed = tri.max_overhang(
            model, model.x_floor_min, bottom, width, DEFAULT_CONFIG
        )
        self.assertLess(allowed, geometric)
        self.assertAlmostEqual(
            allowed, DEFAULT_CONFIG.wedge_overhang_fraction * width, places=6
        )

    def test_the_overhang_cap_keeps_support_above_the_official_floor(self):
        """o <= 0.4w is what the 0.6 support ratio allows; we stay under it."""
        fraction = DEFAULT_CONFIG.wedge_overhang_fraction
        implied_support = 1.0 - fraction
        self.assertGreater(implied_support, DEFAULT_CONFIG.min_support_ratio)
        self.assertLess(fraction, 0.4)

    def test_recovered_area_never_exceeds_the_wedge(self):
        """Counting "everything left of the floor limit" also counts space
        above the chamfer top, which was never wedge."""
        from rule_alpha import triangle as tri

        _container, model = _model()
        tall = AABB(
            (model.x_wall_min + 0.3, 0.0, model.z_floor + 0.6),
            (0.6, 0.4, 1.2), "tall",
        )
        area = tri.wedge_overlap_area(model, tall)
        self.assertLessEqual(area, model.slope_wedge_area + 1e-6)
        self.assertGreater(area, 0.0)

    def test_no_step_material_means_closed(self):
        """Cap customers are worthless without something to build the stairs."""
        from rule_alpha import triangle as tri

        _container, model = _model()
        soft_only = self._profiles([((0.5, 0.4, 0.3), {"soft": True})] * 8)
        demand = tri.measure_demand(soft_only, model, DEFAULT_CONFIG)
        self.assertEqual(demand.p_step, 0.0)
        self.assertGreater(demand.p_cap, 0.0)
        state = tri.evaluate(model, [], demand, 0.0, 0.0, DEFAULT_CONFIG)
        self.assertEqual(state.state, tri.STATE_CLOSED)

    def test_a_mixed_stream_starts_raw_and_a_full_board_closes(self):
        from rule_alpha import triangle as tri

        _container, model = _model()
        mixed = self._profiles(
            [((0.35, 0.30, 0.20), {})] * 4
            + [((0.5, 0.4, 0.3), {"soft": True})] * 4
        )
        demand = tri.measure_demand(mixed, model, DEFAULT_CONFIG)
        self.assertGreater(demand.p_step, 0.0)

        early = tri.evaluate(model, [], demand, 0.0, 0.0, DEFAULT_CONFIG)
        self.assertEqual(early.state, tri.STATE_RAW)

        late = tri.evaluate(model, [], demand, 0.95, 1.0, DEFAULT_CONFIG)
        self.assertEqual(late.state, tri.STATE_CLOSED)
        self.assertLess(late.score, early.score)

    def test_the_strip_is_held_for_step_material_then_released(self):
        from rule_alpha import triangle as tri

        _container, model = _model()
        small = self._profiles([((0.35, 0.30, 0.20), {})])[0]
        big = self._profiles([((0.75, 0.55, 0.30), {})])[0]
        soft = self._profiles([((0.5, 0.4, 0.3), {"soft": True})])[0]

        growing = tri.WedgeState(state=tri.STATE_STAIRCASE, score=1.0)
        capping = tri.WedgeState(state=tri.STATE_SOFT_READY, score=1.0)
        closed = tri.WedgeState(state=tri.STATE_CLOSED, score=-1.0)

        self.assertTrue(
            tri.strip_reserved_for(small, growing, model, DEFAULT_CONFIG)
        )
        self.assertFalse(
            tri.strip_reserved_for(big, growing, model, DEFAULT_CONFIG)
        )
        self.assertFalse(
            tri.strip_reserved_for(soft, growing, model, DEFAULT_CONFIG)
        )
        # once the climb is done the top is for soft
        self.assertTrue(
            tri.strip_reserved_for(soft, capping, model, DEFAULT_CONFIG)
        )
        # and a closed zone takes anything
        self.assertTrue(tri.strip_reserved_for(big, closed, model, DEFAULT_CONFIG))

    def test_a_step_must_rest_on_the_step_below(self):
        from rule_alpha import triangle as tri
        from rule_alpha.geometry import Rect

        _container, model = _model()
        support = Rect(model.x_floor_min, model.x_floor_min + 0.45, -0.2, 0.2)
        bottom = model.z_floor + 0.22
        legal = AABB(
            (model.x_floor_min - 0.08 + 0.20, 0.0, bottom + 0.10),
            (0.40, 0.35, 0.20), "step",
        )
        greedy = AABB(
            (model.x_floor_min - 0.30 + 0.20, 0.0, bottom + 0.10),
            (0.40, 0.35, 0.20), "step",
        )
        self.assertTrue(tri.is_wedge_step(legal, support, model, DEFAULT_CONFIG))
        self.assertFalse(tri.is_wedge_step(greedy, support, model, DEFAULT_CONFIG))


class TallPerimeterTest(unittest.TestCase):
    def test_prime_foundation_material_still_lies_flat(self):
        """Without a footprint cap a stream of big hard boxes stands every item
        on end and Layer 1 keeps no flat surface at all."""
        _container, model = _model()
        big = {
            "index": 0, "length": 0.75, "width": 0.56, "height": 0.30,
            "mass": 15.0, "is_soft": False, "is_prioritized": False,
        }
        profile = cls.classify_item(0, big, DEFAULT_CONFIG)
        standing = max(profile.orientations, key=lambda o: o.dz)
        box = AABB(
            (model.floor_rect.x_max - standing.dx / 2.0, 0.0,
             model.z_floor + standing.dz / 2.0),
            (standing.dx, standing.dy, standing.dz), "probe",
        )
        self.assertGreater(standing.dz, DEFAULT_CONFIG.tall_perimeter_min_height)
        self.assertFalse(
            layer1.is_tall_perimeter(box, model, profile, standing, DEFAULT_CONFIG)
        )

    def test_an_awkward_tall_box_may_stand_against_a_wall(self):
        _container, model = _model()
        awkward = {
            "index": 1, "length": 0.55, "width": 0.40, "height": 0.30,
            "mass": 9.0, "is_soft": False, "is_prioritized": False,
        }
        profile = cls.classify_item(1, awkward, DEFAULT_CONFIG)
        standing = max(profile.orientations, key=lambda o: o.dz)
        at_wall = AABB(
            (model.floor_rect.x_max - standing.dx / 2.0, 0.0,
             model.z_floor + standing.dz / 2.0),
            (standing.dx, standing.dy, standing.dz), "probe",
        )
        in_middle = AABB(
            (0.1, 0.0, model.z_floor + standing.dz / 2.0),
            (standing.dx, standing.dy, standing.dz), "probe",
        )
        self.assertTrue(
            layer1.is_tall_perimeter(at_wall, model, profile, standing, DEFAULT_CONFIG)
        )
        self.assertFalse(
            layer1.is_tall_perimeter(in_middle, model, profile, standing, DEFAULT_CONFIG)
        )

    def test_a_soft_item_never_stands_at_the_perimeter(self):
        _container, model = _model()
        bag = {
            "index": 2, "length": 0.55, "width": 0.40, "height": 0.30,
            "mass": 9.0, "is_soft": True, "is_prioritized": False,
        }
        profile = cls.classify_item(2, bag, DEFAULT_CONFIG)
        standing = max(profile.orientations, key=lambda o: o.dz)
        box = AABB(
            (model.floor_rect.x_max - standing.dx / 2.0, 0.0,
             model.z_floor + standing.dz / 2.0),
            (standing.dx, standing.dy, standing.dz), "probe",
        )
        self.assertFalse(
            layer1.is_tall_perimeter(box, model, profile, standing, DEFAULT_CONFIG)
        )


class RoutingTest(unittest.TestCase):
    def _board(self):
        priority = make_container_dict(index=0, is_prioritized=True,
                                       require_shelf=True, **ULD)
        normal = make_container_dict(index=1, offset_x=2.5, **ULD)
        return layer1.Board([priority, normal], DEFAULT_CONFIG)

    def _profile(self, **flags):
        item = {
            "index": 0, "length": 0.6, "width": 0.4, "height": 0.3, "mass": 8.0,
            "is_soft": flags.get("soft", False),
            "is_prioritized": flags.get("priority", False),
        }
        return cls.classify_item(0, item, DEFAULT_CONFIG)

    def test_soft_only_never_enters_a_priority_container(self):
        board = self._board()
        order = layer1.routing_order(self._profile(soft=True), board, DEFAULT_CONFIG)
        self.assertNotIn(0, order)
        self.assertIn(1, order)

    def test_priority_and_soft_priority_prefer_the_priority_container(self):
        board = self._board()
        for flags in ({"priority": True}, {"soft": True, "priority": True}):
            order = layer1.routing_order(self._profile(**flags), board, DEFAULT_CONFIG)
            self.assertEqual(order[0], 0)

    def test_plain_hard_prefers_the_normal_container_but_may_use_the_priority_one(self):
        board = self._board()
        order = layer1.routing_order(self._profile(), board, DEFAULT_CONFIG)
        self.assertEqual(order[0], 1)
        self.assertIn(0, order)


class EpisodeTest(unittest.TestCase):
    """One short end-to-end run, checked for self-consistency."""

    @classmethod
    def setUpClass(cls_):
        from rule_alpha.episode import run_episode
        from rule_alpha.scenarios import Scenario, _normal_container, _stream

        scenario = Scenario(
            name="unit-test",
            description="short mixed stream",
            containers=[_normal_container()],
            items=_stream(4242, 12, soft_ratio=0.25, priority_ratio=0.15),
        )
        cls_.scenario = scenario
        cls_.result = run_episode(scenario, DEFAULT_CONFIG, snapshot_steps=0)

    def test_something_gets_placed(self):
        self.assertGreater(self.result.summary["items_placed"], 3)

    def test_every_placement_is_valid_against_the_board_before_it(self):
        board = layer1.Board(self.result.containers_raw, DEFAULT_CONFIG)
        for placement in self.result.sequence:
            model = board.model(placement.container_idx)
            container = board.container(placement.container_idx)
            valid, why = layer1.validate(
                placement.box, model, container, DEFAULT_CONFIG
            )
            self.assertTrue(
                valid,
                f"item {placement.profile.index} was accepted but re-validates "
                f"as {why}",
            )
            board.apply(placement)

    def test_layer_one_stays_on_floor_and_shelves(self):
        for placement in self.result.sequence:
            if placement.surface == "item":
                # the one documented exception to floor-and-shelves: a wedge
                # staircase step rests on the step below it
                self.assertEqual(placement.role, cls.ROLE_WEDGE_STEP)
            else:
                self.assertIn(placement.surface, ("floor", "shelf"))

    def test_no_plain_floor_placement_stands_on_a_small_face(self):
        for placement in self.result.sequence:
            if placement.surface != "floor" or placement.role != cls.ROLE_NONE:
                continue
            if placement.profile.is_elongated and not placement.profile.is_soft:
                continue
            self.assertGreaterEqual(
                placement.orientation.footprint + 1e-9,
                DEFAULT_CONFIG.min_floor_footprint_fraction
                * placement.profile.max_footprint,
            )

    def test_tall_poses_always_have_a_wall_or_a_backing_item(self):
        board = layer1.Board(self.result.containers_raw, DEFAULT_CONFIG)
        for placement in self.result.sequence:
            if placement.orientation.tipping_ratio >= DEFAULT_CONFIG.max_freestanding_ratio:
                model = board.model(placement.container_idx)
                container = board.container(placement.container_idx)
                self.assertTrue(
                    layer1._has_backing(placement.box, model, container, DEFAULT_CONFIG),
                    f"item {placement.profile.index} stands free at "
                    f"R={placement.orientation.tipping_ratio:.2f}",
                )
            board.apply(placement)

    def test_summary_carries_the_required_diagnostics(self):
        container = self.result.summary["containers"][0]
        for key in ("flatness", "holes", "wall_front", "corridor",
                    "support_type_area", "floor_coverage"):
            self.assertIn(key, container)
        for key in ("largest_plateau_area", "largest_plateau_ratio",
                    "plateau_count", "height_spread", "local_roughness"):
            self.assertIn(key, container["flatness"])
        for key in ("interior_hole_count", "largest_interior_hole",
                    "largest_open_free_area"):
            self.assertIn(key, container["holes"])
        self.assertIn("wall_height_ratio", container["wall_front"])

    def test_step_log_round_trips_as_jsonl(self):
        import json

        lines = self.result.to_jsonl().strip().splitlines()
        records = [json.loads(line) for line in lines]
        self.assertEqual(records[0]["record"], "scenario")
        self.assertEqual(records[-1]["record"], "summary")
        steps = [r for r in records if r["record"] == "step"]
        self.assertEqual(len(steps), len(self.result.sequence))
        for step in steps:
            for key in ("item_index", "class", "role", "archetype", "reason",
                        "orientation", "dx", "dy", "dz", "footprint",
                        "tipping_ratio", "tipping_band", "surface",
                        "candidate_count_by_archetype", "veto_count_by_rule",
                        "transport_ok", "settle_ok", "board"):
                self.assertIn(key, step)


class ProductionPolicyUntouchedTest(unittest.TestCase):
    def test_reuse_bridge_loads_the_production_helpers(self):
        from rule_alpha import _reuse

        self.assertTrue(callable(_reuse.transport_samples))
        self.assertTrue(hasattr(_reuse.Geometry, "support_ratio"))

    def test_rule_alpha_is_not_imported_by_the_production_agent(self):
        source = (REPO_ROOT / "agent" / "agent.py").read_text(encoding="utf-8")
        self.assertNotIn("rule_alpha", source)


if __name__ == "__main__":
    unittest.main()
