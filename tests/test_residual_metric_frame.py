from __future__ import annotations

import unittest

from scripts.measure_residual_metric_defect import (
    container_centres,
    to_container_frame,
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


if __name__ == "__main__":
    unittest.main()
