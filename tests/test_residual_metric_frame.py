from __future__ import annotations

import unittest

from scripts.measure_residual_metric_defect import (
    container_centres,
    to_container_frame,
)
from scripts.residual_diversity import (
    consumption_distance,
    occupancy_distance,
    occupancy_scales,
)


class ContainerFrameTests(unittest.TestCase):
    def centres(self):
        return container_centres(
            {
                "observation": {
                    "container_list": [
                        {"index": 0, "center": [0.0, 0.0, 0.805]},
                        {"index": 1, "center": [2.5, 0.0, 0.805]},
                    ]
                }
            }
        )

    def record(self, container: int, center: list[float]) -> dict:
        return {"container_index": container, "center": list(center)}

    def test_the_container_offset_is_removed_from_x_and_y(self):
        # The defect: settled positions are world, commands are
        # container-local, and the containers sit 2.5 m apart -- against item
        # extents of tens of centimetres.
        shifted = to_container_frame(
            self.record(1, [3.171, 0.4, 0.175]), self.centres()
        )

        self.assertAlmostEqual(shifted["center"][0], 0.671)
        self.assertAlmostEqual(shifted["center"][1], 0.4)

    def test_z_is_left_alone(self):
        # A commanded z of 0.227 settling to 0.175 is the item dropping five
        # centimetres. Subtracting the container centre's z would turn that
        # physical fact into a frame error.
        shifted = to_container_frame(
            self.record(1, [3.171, 0.0, 0.175]), self.centres()
        )

        self.assertAlmostEqual(shifted["center"][2], 0.175)

    def test_the_first_container_is_untouched(self):
        original = self.record(0, [-0.106, 0.388, 0.175])

        shifted = to_container_frame(original, self.centres())

        self.assertEqual(shifted["center"], original["center"])

    def test_an_unknown_container_is_returned_unchanged(self):
        original = self.record(7, [1.0, 2.0, 3.0])

        self.assertIs(to_container_frame(original, self.centres()), original)

    def test_the_input_record_is_not_mutated(self):
        original = self.record(1, [3.171, 0.0, 0.175])

        to_container_frame(original, self.centres())

        self.assertAlmostEqual(original["center"][0], 3.171)


class ComponentDistanceTests(unittest.TestCase):
    """The single Gower sum answered two questions at once. Split it."""

    def settled(
        self,
        *,
        pool_index: int = 0,
        item_index: int = 0,
        container_index: int = 0,
        center: tuple[float, float, float] = (0.0, 0.0, 0.2),
    ) -> dict:
        return {
            "pool_index": pool_index,
            "item_index": item_index,
            "container_index": container_index,
            "orientation": 0,
            "kind": "candidate",
            "center": list(center),
            "size": [0.3, 0.2, 0.15],
            "settle_tilt_deg": 0.0,
        }

    def scales(self, records: list[dict]) -> tuple[float, ...]:
        return occupancy_scales(records)

    def test_occupancy_does_not_index_past_its_own_field_list(self):
        # The component vector carries one categorical field, not the four
        # the full descriptor has. Reading the count from the module-level
        # tuple raised IndexError here.
        left = self.settled(center=(0.0, 0.0, 0.2))
        right = self.settled(center=(0.5, 0.0, 0.2))

        value = occupancy_distance(
            left, right, scales=self.scales([left, right])
        )

        self.assertGreater(value, 0.0)

    def test_occupancy_ignores_which_item_was_consumed(self):
        left = self.settled(pool_index=0, item_index=0)
        right = self.settled(pool_index=3, item_index=9)
        scales = self.scales([left, right])

        self.assertEqual(occupancy_distance(left, right, scales=scales), 0.0)

    def test_occupancy_counts_a_different_container(self):
        # Container membership is carried once, here, instead of also by a
        # 2.5 m offset in the position term.
        left = self.settled(container_index=0)
        right = self.settled(container_index=1)

        self.assertEqual(
            occupancy_distance(left, right, scales=self.scales([left, right])),
            1.0,
        )

    def test_consumption_ignores_where_the_item_landed(self):
        left = self.settled(center=(0.0, 0.0, 0.2))
        right = self.settled(center=(0.9, 0.7, 0.5))

        self.assertEqual(consumption_distance(left, right), 0.0)

    def test_consumption_counts_a_different_item(self):
        left = self.settled(pool_index=0, item_index=0)
        right = self.settled(pool_index=1, item_index=4)

        self.assertEqual(consumption_distance(left, right), 1.0)

    def test_consumption_is_a_fraction_when_only_one_field_differs(self):
        left = self.settled(pool_index=0, item_index=0)
        right = self.settled(pool_index=0, item_index=4)

        self.assertAlmostEqual(consumption_distance(left, right), 0.5)


if __name__ == "__main__":
    unittest.main()
