from __future__ import annotations

import unittest

from scripts.develop_post_shake_soft_reranker import (
    soft_topology_delta,
    soft_topology_summary,
)


def state(items: list[list[float]]) -> dict:
    return {
        "container_features": ["length", "width", "height"],
        "container_values": [[2.0, 1.0, 1.5]],
        "packed_item_features": [
            "container_index", "local_x", "local_y", "local_z",
            "length", "width", "height", "mass", "is_prioritized", "is_soft",
        ],
        "packed_item_values": items,
        "visible_item_features": [],
        "visible_item_values": [],
    }


class PostShakeSoftRerankerTests(unittest.TestCase):
    def test_direct_ordinary_cover_is_counted(self) -> None:
        lower_soft = [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]
        upper_plain = [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 0]

        values = soft_topology_summary(state([lower_soft, upper_plain]))

        self.assertEqual(values[3:7], [1.0, 1.0, 1.0, 1.0])

    def test_soft_on_soft_is_not_a_soft_violation(self) -> None:
        lower_soft = [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]
        upper_soft = [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 1]

        values = soft_topology_summary(state([lower_soft, upper_soft]))

        self.assertEqual(values[3:7], [0.0, 0.0, 0.0, 0.0])

    def test_priority_is_independent_of_soft_on_all_upper_classes(self) -> None:
        lower_soft = [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]
        for upper_priority, upper_soft, expected in (
            (0, 0, 1.0), (1, 0, 1.0), (0, 1, 0.0), (1, 1, 0.0),
        ):
            with self.subTest(priority=upper_priority, soft=upper_soft):
                upper = [
                    0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3,
                    upper_priority, upper_soft,
                ]
                values = soft_topology_summary(state([lower_soft, upper]))
                self.assertEqual(values[3], expected)

    def test_soft_topology_delta_negates_when_afterstates_swap(self) -> None:
        clean = state([[0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1]])
        covered = state([
            [0, 0, 0, 0.10, 0.4, 0.4, 0.2, 2, 0, 1],
            [0, 0, 0, 0.30, 0.3, 0.3, 0.2, 3, 0, 0],
        ])
        row = {
            "lower_afterstate_tensor": clean,
            "higher_afterstate_tensor": covered,
        }

        forward = soft_topology_delta(row)
        reverse = soft_topology_delta(row, (covered, clean))

        self.assertEqual(reverse, [-value for value in forward])


if __name__ == "__main__":
    unittest.main()
