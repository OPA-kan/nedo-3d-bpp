"""
The board features are a ranking signal, so the tests pin the direction of
each one against a hand-built board rather than its absolute value.
"""
import unittest

import numpy as np

from agent import agent as A


def container(length=1.0, width=1.0, height=1.0, thickness=0.0):
    return {
        "index": 0,
        "length": length,
        "width": width,
        "height": height,
        "thickness": thickness,
        "buffer": 0.0,
        "cut_x": 0.0,
        "cut_y": 0.0,
        "require_shelf": False,
        "is_prioritized": False,
        "packed_items": [],
    }


def box(center, size):
    return A.AABB(center=tuple(center), size=tuple(size), name="packed_item")


class GridTests(unittest.TestCase):
    def test_the_grid_covers_the_interior_and_nothing_else(self):
        grid = A.board_grid(container(length=1.0, width=0.5, thickness=0.05))

        self.assertGreater(len(grid.xs), 0)
        self.assertGreaterEqual(float(grid.xs.min()), -0.45)
        self.assertLessEqual(float(grid.xs.max()), 0.45)
        self.assertGreaterEqual(float(grid.ys.min()), -0.20)
        self.assertLessEqual(float(grid.ys.max()), 0.20)

    def test_a_container_without_half_spaces_still_yields_a_usable_board(self):
        """
        Observations may omit points/n_vecs. Falling back to the nominal
        interior keeps the features defined instead of reporting a board
        that accepts nothing.
        """
        grid = A.board_grid(container())

        self.assertTrue(grid.usable.all())
        self.assertTrue(np.isfinite(grid.floor).all())
        self.assertTrue(np.isfinite(grid.ceiling).all())

    def test_the_grid_is_cached_by_value_not_identity(self):
        first = A.board_grid(container())
        second = A.board_grid(container())

        self.assertIs(first, second)


class OccupancyTests(unittest.TestCase):
    def test_an_empty_board_is_flat_at_the_floor_with_nothing_filled(self):
        target = container()
        grid = A.board_grid(target)

        top, filled, _landable = A.board_occupancy(target, grid)

        self.assertTrue(np.allclose(top, grid.floor))
        self.assertTrue(np.allclose(filled, 0.0))

    def test_a_stamped_box_raises_the_surface_only_under_itself(self):
        target = container()
        grid = A.board_grid(target)
        top, filled, _landable = A.board_occupancy(target, grid)
        top = top.copy()
        filled = filled.copy()

        A._board_stamp(grid, top, filled, box((0.0, 0.0, 0.1), (0.2, 0.2, 0.2)))

        raised = top > grid.floor + 1e-9
        self.assertTrue(raised.any())
        self.assertFalse(raised.all())
        self.assertAlmostEqual(float(top[raised].max()), 0.2, places=6)


class SealedVolumeTests(unittest.TestCase):
    def test_a_box_resting_on_the_floor_seals_nothing(self):
        target = container()
        grid = A.board_grid(target)
        top, filled, _landable = A.board_occupancy(target, grid)
        top, filled = top.copy(), filled.copy()
        A._board_stamp(grid, top, filled, box((0.0, 0.0, 0.1), (0.2, 0.2, 0.2)))

        features = A.board_features(grid, top, filled, [])

        self.assertAlmostEqual(features.sealed_volume, 0.0, places=9)

    def test_a_box_bridging_a_gap_seals_the_void_beneath_it(self):
        """
        The whole point of H: a lid over empty space is volume that no later
        placement can reclaim, and it is invisible to a surface-only metric.
        """
        target = container()
        grid = A.board_grid(target)
        top, filled, _landable = A.board_occupancy(target, grid)
        top, filled = top.copy(), filled.copy()

        A._board_stamp(grid, top, filled, box((0.0, 0.0, 0.25), (0.2, 0.2, 0.1)))
        features = A.board_features(grid, top, filled, [])

        self.assertGreater(features.sealed_volume, 0.0)
        # 0.2 x 0.2 footprint over a 0.2 m gap, up to one cell of quantisation.
        self.assertLess(abs(features.sealed_volume - 0.2 * 0.2 * 0.2), 0.004)


class RoughnessTests(unittest.TestCase):
    def test_a_flat_board_is_smoother_than_a_stepped_one(self):
        target = container()
        grid = A.board_grid(target)

        flat_top, flat_filled, _fl = A.board_occupancy(target, grid)
        flat = A.board_features(grid, flat_top.copy(), flat_filled.copy(), [])

        stepped_top, stepped_filled, _sl = A.board_occupancy(target, grid)
        stepped_top, stepped_filled = stepped_top.copy(), stepped_filled.copy()
        A._board_stamp(
            grid, stepped_top, stepped_filled, box((0.2, 0.2, 0.15), (0.2, 0.2, 0.3))
        )
        stepped = A.board_features(grid, stepped_top, stepped_filled, [])

        self.assertGreater(stepped.roughness, flat.roughness)


class ProbeShapeTests(unittest.TestCase):
    def test_shapes_are_deduplicated_and_ordered_by_footprint(self):
        items = [
            {"length": 0.1, "width": 0.1, "height": 0.1},
            {"length": 0.4, "width": 0.3, "height": 0.2},
        ]

        shapes = A.board_probe_shapes(items)

        footprints = [round(dx * dy, 6) for dx, dy, _dz in shapes]
        self.assertEqual(footprints, sorted(footprints, reverse=True))
        self.assertEqual(len(shapes), len(set((dx, dy) for dx, dy, _ in shapes)))

    def test_a_footprint_takes_the_smallest_height_that_produces_it(self):
        """
        Headroom is the constraint, and the board should be credited with
        the easiest orientation that yields the footprint.
        """
        shapes = A.board_probe_shapes(
            [{"length": 0.4, "width": 0.4, "height": 0.1}]
        )

        square = [dz for dx, dy, dz in shapes if abs(dx - 0.4) < 1e-9 and abs(dy - 0.4) < 1e-9]
        self.assertTrue(square)
        self.assertAlmostEqual(min(square), 0.1, places=6)

    def test_the_probe_set_is_capped(self):
        items = [
            {"length": 0.1 * n, "width": 0.05 * n, "height": 0.02 * n}
            for n in range(1, 12)
        ]

        self.assertLessEqual(len(A.board_probe_shapes(items)), A.BOARD_PROBE_SHAPES)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.target = container(length=1.0, width=1.0, height=0.5)
        self.grid = A.board_grid(self.target)

    def features(self, boxes, shapes):
        top, filled, _landable = A.board_occupancy(self.target, self.grid)
        top, filled = top.copy(), filled.copy()
        for item in boxes:
            A._board_stamp(self.grid, top, filled, item)
        return A.board_features(self.grid, top, filled, shapes)

    def test_an_empty_board_accepts_everything_that_fits(self):
        shapes = [(0.2, 0.2, 0.2), (0.4, 0.4, 0.4)]

        features = self.features([], shapes)

        self.assertEqual(features.accepted_shapes, 2)
        self.assertGreater(features.alternativity, 0)

    def test_a_shape_taller_than_the_headroom_is_not_accepted(self):
        features = self.features([], [(0.2, 0.2, 5.0)])

        self.assertEqual(features.accepted_shapes, 0)

    def test_a_pillar_destroys_breadth_for_the_large_shape_only(self):
        """
        Acceptance breadth is the point: a placement that leaves no flat
        region wide enough for the big footprint has lost that shape even
        though plenty of volume remains.
        """
        pillars = [
            box((-0.3, -0.3, 0.1), (0.1, 0.1, 0.2)),
            box((0.0, 0.0, 0.1), (0.1, 0.1, 0.2)),
            box((0.3, 0.3, 0.1), (0.1, 0.1, 0.2)),
            box((-0.3, 0.3, 0.1), (0.1, 0.1, 0.2)),
            box((0.3, -0.3, 0.1), (0.1, 0.1, 0.2)),
        ]
        shapes = [(0.9, 0.9, 0.1), (0.1, 0.1, 0.1)]

        empty = self.features([], shapes)
        littered = self.features(pillars, shapes)

        self.assertEqual(empty.accepted_shapes, 2)
        self.assertEqual(littered.accepted_shapes, 1)

    def sites(self, boxes, shape):
        top, filled, _landable = A.board_occupancy(self.target, self.grid)
        top, filled = top.copy(), filled.copy()
        for item in boxes:
            A._board_stamp(self.grid, top, filled, item)
        return A._board_site_count(
            self.grid, top, self.grid.ceiling - top, shape
        )

    def test_site_count_falls_as_the_board_fills_without_losing_breadth(self):
        """
        Measured before the cap, because the cap is what makes forty sites
        and forty-one indistinguishable on purpose.
        """
        shape = (0.2, 0.2, 0.1)
        wall = [box((-0.25, 0.0, 0.1), (0.4, 0.9, 0.2))]

        empty = self.sites([], shape)
        crowded = self.sites(wall, shape)

        self.assertGreater(crowded, 0)
        self.assertLess(crowded, empty)
        self.assertEqual(
            self.features([], [shape]).accepted_shapes,
            self.features(wall, [shape]).accepted_shapes,
        )

    def test_alternativity_saturates_at_the_cap_per_shape(self):
        shapes = [(0.05, 0.05, 0.05)] * 3

        features = self.features([], shapes)

        self.assertLessEqual(features.alternativity, 3 * A.BOARD_SITE_CAP)


class ReleaseCandidateTests(unittest.TestCase):
    """
    Release candidates are commanded above their resting height and fall.
    Reading the board at the commanded height evaluates a state that never
    exists, and it is the only candidate kind left once the settled heap
    empties -- exactly the situation at the end of an episode.
    """

    def setUp(self):
        self.target = container(length=1.0, width=1.0, height=1.0)
        self.shapes = [(0.2, 0.2, 0.2)]

    def test_a_release_candidate_is_read_where_it_will_rest(self):
        commanded = A.AABB(
            center=(0.0, 0.0, 0.6), size=(0.2, 0.2, 0.2),
            name="release_candidate",
        )
        rested = A.AABB(
            center=(0.0, 0.0, 0.1), size=(0.2, 0.2, 0.2),
            name="packed_item",
        )

        floating = A.board_features_after(self.target, commanded, self.shapes)
        landed = A.board_features_after(self.target, rested, self.shapes)

        self.assertAlmostEqual(
            floating.sealed_volume, landed.sealed_volume, places=9
        )
        self.assertEqual(floating.rank_key(), landed.rank_key())

    def test_a_settled_candidate_is_read_where_it_was_placed(self):
        """The proxy must not move a candidate that is not a release."""
        bridging = A.AABB(
            center=(0.0, 0.0, 0.6), size=(0.2, 0.2, 0.2), name="candidate"
        )

        features = A.board_features_after(self.target, bridging, self.shapes)

        self.assertGreater(features.sealed_volume, 0.0)


class RankKeyTests(unittest.TestCase):
    def test_breadth_outranks_tidiness(self):
        broad = A.BoardFeatures(3, 4, 2, 0.5, 9.0)
        tidy = A.BoardFeatures(2, 4, 99, 0.0, 0.0)

        self.assertGreater(broad.rank_key(), tidy.rank_key())

    def test_a_sealed_void_loses_to_an_open_one_at_equal_breadth(self):
        open_board = A.BoardFeatures(3, 4, 5, 0.01, 1.0)
        sealed = A.BoardFeatures(3, 4, 5, 0.40, 1.0)

        self.assertGreater(open_board.rank_key(), sealed.rank_key())


class SelectionTests(unittest.TestCase):
    def test_board_is_a_recognised_selection_mode(self):
        self.assertEqual(A.normalized_lookahead_mode("board"), "board")

    def test_the_board_choice_prefers_the_candidate_that_keeps_breadth(self):
        """
        Two candidates the ranker scores identically: one lands flat on the
        floor, the other bridges a gap and seals it. The board must pick the
        first even though the incumbent score cannot tell them apart.
        """
        target = container(length=1.0, width=1.0, height=0.5)
        observation = {"container_list": [target]}
        item = {"length": 0.2, "width": 0.2, "height": 0.2}

        def decision(center):
            return A.PlacementDecision(
                action={
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": np.zeros(3, dtype=np.float32),
                    "orientation": 0,
                },
                candidate=box(center, (0.2, 0.2, 0.2)),
                score=1.0,
            )

        grounded = decision((0.0, 0.0, 0.1))
        bridging = decision((0.0, 0.0, 0.35))

        agent = A.Agent.__new__(A.Agent)
        agent.last_board_features = None
        chosen = agent._board_choice(
            [bridging, grounded], observation, [(0, item)]
        )

        self.assertIs(chosen, grounded)
        self.assertIsNotNone(agent.last_board_features)

    def test_a_single_candidate_is_returned_unchanged(self):
        target = container()
        observation = {"container_list": [target]}
        only = A.PlacementDecision(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": np.zeros(3, dtype=np.float32),
                "orientation": 0,
            },
            candidate=box((0.0, 0.0, 0.1), (0.2, 0.2, 0.2)),
            score=1.0,
        )

        agent = A.Agent.__new__(A.Agent)
        agent.last_board_features = None

        self.assertIs(
            agent._board_choice(
                [only],
                observation,
                [(0, {"length": 0.2, "width": 0.2, "height": 0.2})],
            ),
            only,
        )

    def test_no_probe_shapes_falls_back_to_the_ranker_order(self):
        target = container()
        observation = {"container_list": [target]}
        decisions = [
            A.PlacementDecision(
                action={
                    "item_idx": index,
                    "container_idx": 0,
                    "place_pos": np.zeros(3, dtype=np.float32),
                    "orientation": 0,
                },
                candidate=box((0.0, 0.0, 0.1), (0.2, 0.2, 0.2)),
                score=float(index),
            )
            for index in range(2)
        ]

        agent = A.Agent.__new__(A.Agent)
        agent.last_board_features = None

        self.assertIs(
            agent._board_choice(decisions, observation, []), decisions[0]
        )


class DefaultTests(unittest.TestCase):
    def test_the_first_pass_depth_is_the_measured_one(self):
        """
        Moved 64 -> 256 on two paired blocks (9W/0L/1T, p = 0.0039) at
        unchanged total attempts per step. Pinned so the value cannot drift
        back without the measurement being revisited.
        """
        self.assertEqual(A.ANCHOR_FIRST_PASS_ATTEMPTS, 256)

    def test_the_shipped_selection_mode_is_unchanged(self):
        """
        The board evaluator is measured before it ships. Until then the
        default path must be byte-identical to the run that produced the
        submission on record.
        """
        self.assertEqual(A.LOOKAHEAD_SELECTION_MODE, "weighted")


if __name__ == "__main__":
    unittest.main()


class LandabilityTests(unittest.TestCase):
    """
    The instrument check for BOARD_LANDABLE_ONLY, run before the feature is
    used for anything.

    support_surfaces() excludes soft and priority items from being support,
    so the agent never generates a placement resting on one. board_occupancy
    stamped every packed item into the height map regardless, so the board
    features counted landing sites the search cannot reach -- one of the two
    structural causes behind 123 reported sites at a state where an
    exhaustive oracle found zero
    (board-receptivity-is-not-a-feasibility-predictor).
    """

    def packed(self, x, y, z, dx, dy, dz, soft=False, priority=False):
        return {
            "index": 0,
            "length": dx,
            "width": dy,
            "height": dz,
            "mass": 5.0,
            "is_soft": soft,
            "is_prioritized": priority,
            "pos": [x, y, z],
            "orientation": 0,
        }

    def occupancy(self, packed_items):
        target = container(length=1.0, width=1.0, height=1.0)
        target["packed_items"] = packed_items
        grid = A.board_grid(target)
        top, filled, landable = A.board_occupancy(target, grid)
        return grid, top, filled, landable

    def test_a_normal_box_stays_landable(self):
        grid, _top, _filled, landable = self.occupancy(
            [self.packed(0.0, 0.0, 0.1, 0.4, 0.4, 0.2)]
        )
        self.assertTrue(landable.all())

    def test_a_soft_box_makes_its_own_columns_unlandable(self):
        grid, top, _filled, landable = self.occupancy(
            [self.packed(0.0, 0.0, 0.1, 0.4, 0.4, 0.2, soft=True)]
        )
        raised = top > grid.floor + 1e-9
        self.assertTrue(raised.any(), "the soft box should raise the surface")
        self.assertFalse(
            landable[raised].any(),
            "no column topped by a soft item may be landable",
        )
        self.assertTrue(
            landable[~raised].all(),
            "columns the soft box does not cover stay landable",
        )

    def test_a_priority_box_behaves_the_same_way(self):
        grid, top, _filled, landable = self.occupancy(
            [self.packed(0.0, 0.0, 0.1, 0.4, 0.4, 0.2, priority=True)]
        )
        self.assertFalse(landable[top > grid.floor + 1e-9].any())

    def test_a_normal_box_stacked_above_a_soft_one_restores_landability(self):
        """
        The flag follows the HIGHEST stamp. A normal item resting above a
        soft one is a legal support again, so the column comes back.
        """
        grid, _top, _filled, landable = self.occupancy(
            [
                self.packed(0.0, 0.0, 0.1, 0.4, 0.4, 0.2, soft=True),
                self.packed(0.0, 0.0, 0.3, 0.4, 0.4, 0.2),
            ]
        )
        self.assertTrue(landable.all())

    def test_the_site_count_drops_when_landability_is_required(self):
        """
        The measurement that matters: requiring landability must actually
        remove sites the old count reported.
        """
        grid, top, _filled, landable = self.occupancy(
            [self.packed(0.0, 0.0, 0.1, 0.6, 0.6, 0.2, soft=True)]
        )
        headroom = grid.ceiling - top
        shape = (0.2, 0.2, 0.1)

        without = A._board_site_count(grid, top, headroom, shape)
        with_flag = A._board_site_count(
            grid, top, headroom, shape, landable=landable
        )

        self.assertGreater(
            without,
            with_flag,
            "the soft top must have been counted before and not after",
        )
