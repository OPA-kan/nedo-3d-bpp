from __future__ import annotations

import unittest

from scripts.residual_diversity import (
    consumption_distance,
    container_frame_offsets,
    occupancy_distance,
    occupancy_scales,
    settled_proxy_record,
)


class ContainerFrameTests(unittest.TestCase):
    """`settled_proxy_record` is where the frame is collapsed, so test it."""

    def offsets(self):
        return container_frame_offsets(
            [
                {"index": 0, "center": [0.0, 0.0, 0.805]},
                {"index": 1, "center": [2.5, 0.0, 0.805]},
            ]
        )

    def settled(self, container: int, center: list[float]) -> dict:
        physical = {
            "x_plus": {
                "position": list(center),
                "aabb_dimensions": [0.3, 0.2, 0.15],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }
        }
        record = {
            "pool_index": 0,
            "item_index": 0,
            "container_index": container,
            "orientation": 0,
            "kind": "candidate",
        }
        return record, physical

    def shift(self, container: int, center: list[float]) -> dict:
        record, physical = self.settled(container, center)
        return settled_proxy_record(
            record, physical, container_offsets=self.offsets()
        )

    def test_the_container_offset_is_removed_from_x_and_y(self):
        # The defect: settled positions are world, commands are
        # container-local, and the containers sit 2.5 m apart -- against item
        # extents of tens of centimetres.
        shifted = self.shift(1, [3.171, 0.4, 0.175])

        self.assertAlmostEqual(shifted["center"][0], 0.671)
        self.assertAlmostEqual(shifted["center"][1], 0.4)

    def test_z_is_left_alone(self):
        # A commanded z of 0.227 settling to 0.175 is the item dropping five
        # centimetres. Subtracting the container centre's z would turn that
        # physical fact into a frame error.
        shifted = self.shift(1, [3.171, 0.0, 0.175])

        self.assertAlmostEqual(shifted["center"][2], 0.175)

    def test_the_first_container_is_untouched(self):
        self.assertEqual(
            self.shift(0, [-0.106, 0.388, 0.175])["center"],
            [-0.106, 0.388, 0.175],
        )

    def test_an_unknown_container_keeps_world_coordinates(self):
        self.assertEqual(
            self.shift(7, [1.0, 2.0, 3.0])["center"], [1.0, 2.0, 3.0]
        )

    def test_omitting_the_offsets_reproduces_the_old_descriptor(self):
        # Every measurement recorded before 2026-08-11 read the world-frame
        # descriptor. The default must keep reproducing it, or those entries
        # stop being readable.
        record, physical = self.settled(1, [3.171, 0.4, 0.175])

        self.assertEqual(
            settled_proxy_record(record, physical)["center"],
            [3.171, 0.4, 0.175],
        )

    def test_a_container_list_without_centres_yields_no_offsets(self):
        self.assertEqual(container_frame_offsets([{"index": 0}]), {})
        self.assertEqual(container_frame_offsets(None), {})


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
