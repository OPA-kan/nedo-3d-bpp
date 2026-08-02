from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_board_value import (  # noqa: E402
    BAGGAGE_TYPES,
    greedy_independent_set,
    hall_statistics,
    maximum_matching,
    subsample,
    type_representative,
)

WORKBOOK = ROOT / "simulator" / "configs" / "item_params.xlsx"


class _StubAgent:
    SETTLED_ITEM_CLEARANCE = 0.026


class _Box:
    """Minimal AABB stand-in: the instrument only reads min/max/name."""

    def __init__(self, center, size, name=""):
        self.center = center
        self.size = size
        self.name = name

    @property
    def minimum(self):
        return [c - s / 2.0 for c, s in zip(self.center, self.size)]

    @property
    def maximum(self):
        return [c + s / 2.0 for c, s in zip(self.center, self.size)]


class BaggagePriorTests(unittest.TestCase):
    def test_prior_matches_the_published_workbook(self) -> None:
        # The prior is the only thing a Task C agent may assume about
        # arrivals it cannot see, so a silent drift from the published
        # table would make every board value wrong in a way no other
        # test would notice.
        if importlib.util.find_spec("openpyxl") is None:
            self.skipTest("openpyxl not installed")
        import openpyxl

        sheet = openpyxl.load_workbook(WORKBOOK).active
        table = {
            str(row[0]): row[2:]
            for row in sheet.iter_rows(values_only=True)
            if row[0] is not None
        }
        self.assertEqual(len(BAGGAGE_TYPES), len(table["length"]))
        for column, entry in enumerate(BAGGAGE_TYPES):
            for field in ("length", "width", "height", "mass"):
                self.assertAlmostEqual(
                    float(entry[field]),
                    float(table[field][column]),
                    places=6,
                    msg=f"{entry['name']}.{field}",
                )
            self.assertEqual(
                bool(entry["is_soft"]),
                bool(table["is_soft"][column]),
                msg=f"{entry['name']}.is_soft",
            )

    def test_representative_never_carries_a_real_pool_index(self) -> None:
        # A prior representative must never be mistaken for a pool item.
        for index, entry in enumerate(BAGGAGE_TYPES):
            representative = type_representative(entry, index)
            self.assertLess(representative["index"], 0)
            self.assertFalse(representative["is_prioritized"])


class GreedyIndependentSetTests(unittest.TestCase):
    def test_disjoint_placements_all_count(self) -> None:
        anchors = [
            _Box((0.0, 0.0, 0.1), (0.2, 0.2, 0.2)),
            _Box((1.0, 0.0, 0.1), (0.2, 0.2, 0.2)),
            _Box((2.0, 0.0, 0.1), (0.2, 0.2, 0.2)),
        ]
        self.assertEqual(greedy_independent_set(_StubAgent(), anchors), 3)

    def test_overlapping_placements_collapse_to_one(self) -> None:
        anchors = [
            _Box((0.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
            _Box((0.05, 0.0, 0.1), (0.4, 0.4, 0.2)),
            _Box((0.1, 0.0, 0.1), (0.4, 0.4, 0.2)),
        ]
        self.assertEqual(greedy_independent_set(_StubAgent(), anchors), 1)

    def test_vertically_separated_placements_do_not_conflict(self) -> None:
        # Matches Stage A's anchors_conflict: stacking is compatible. This
        # is exactly why the count is a bound for the occupancy relation
        # only, not for the theory's wider rho(o).
        anchors = [
            _Box((0.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
            _Box((0.0, 0.0, 0.5), (0.4, 0.4, 0.2)),
        ]
        self.assertEqual(greedy_independent_set(_StubAgent(), anchors), 2)

    def test_empty_input_is_zero(self) -> None:
        self.assertEqual(greedy_independent_set(_StubAgent(), []), 0)


class HallStatisticsTests(unittest.TestCase):
    def test_capacity_is_what_keeps_one_big_floor_from_degenerating(
        self,
    ) -> None:
        # Every class reaches exactly one component. Without capacity the
        # deficiency would be |C| - 1 = 6 no matter how much room that
        # component has, which is the degeneracy the capacitated form
        # exists to remove.
        neighbourhoods = [{(0, 0)} for _ in range(7)]
        uncapacitated = hall_statistics(
            neighbourhoods, {(0, 0): 1}
        )
        self.assertEqual(uncapacitated["hall_deficiency"], 6)
        roomy = hall_statistics(neighbourhoods, {(0, 0): 4})
        self.assertEqual(roomy["hall_deficiency"], 3)
        self.assertAlmostEqual(roomy["hall_ratio"], 4.0 / 7.0)

    def test_independent_resources_leave_no_deficiency(self) -> None:
        neighbourhoods = [{(0, index)} for index in range(7)]
        capacities = {(0, index): 1 for index in range(7)}
        stats = hall_statistics(neighbourhoods, capacities)
        self.assertEqual(stats["hall_deficiency"], 0)
        self.assertAlmostEqual(stats["hall_ratio"], 1.0)

    def test_worst_subset_names_the_competing_classes(self) -> None:
        # Two classes share one single-slot resource; the rest are free.
        neighbourhoods = [{(0, 0)}, {(0, 0)}] + [
            {(0, index)} for index in range(1, 6)
        ]
        capacities = {(0, 0): 1}
        capacities.update({(0, index): 3 for index in range(1, 6)})
        stats = hall_statistics(neighbourhoods, capacities)
        self.assertEqual(stats["hall_deficiency"], 1)
        self.assertEqual(
            sorted(stats["hall_worst_subset"]),
            sorted(
                [BAGGAGE_TYPES[0]["name"], BAGGAGE_TYPES[1]["name"]]
            ),
        )

    def test_a_class_with_no_resource_is_deficient(self) -> None:
        neighbourhoods = [set()] + [
            {(0, index)} for index in range(1, 7)
        ]
        capacities = {(0, index): 1 for index in range(1, 7)}
        stats = hall_statistics(neighbourhoods, capacities)
        self.assertEqual(stats["hall_deficiency"], 1)
        self.assertEqual(stats["hall_ratio"], 0.0)

    def test_matching_never_exceeds_total_capacity(self) -> None:
        neighbourhoods = [{(0, 0), (0, 1)} for _ in range(7)]
        capacities = {(0, 0): 2, (0, 1): 1}
        self.assertEqual(maximum_matching(neighbourhoods, capacities), 3)


class SubsampleTests(unittest.TestCase):
    def test_short_input_is_returned_unchanged(self) -> None:
        items = [1, 2, 3]
        self.assertIs(subsample(items, 10), items)

    def test_subsample_is_deterministic_and_spread(self) -> None:
        items = list(range(100))
        picked = subsample(items, 5)
        self.assertEqual(picked, [0, 20, 40, 60, 80])
        self.assertEqual(picked, subsample(items, 5))

    def test_zero_limit_disables_truncation(self) -> None:
        items = list(range(10))
        self.assertIs(subsample(items, 0), items)


if __name__ == "__main__":
    unittest.main()
