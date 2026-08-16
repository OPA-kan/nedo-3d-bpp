from __future__ import annotations

import unittest

from scripts.develop_distributional_fill_preaction_v6 import (
    GRID_SIZE,
    _stamped_grid,
    grid_pair_vector,
)

ACTION_NAMES = [
    "container_index", "command_x", "command_y", "command_z", "orientation",
    "is_release_candidate", "immediate_score", "length", "width", "height",
    "mass", "is_prioritized", "is_soft", "lateralFriction", "rollingFriction",
    "spinningFriction", "restitution", "angularDamping", "contactStiffness",
    "contactDamping", "linearDamping",
]


def _action(
    *, container: float = 0.0, x: float = 0.0, y: float = 0.0,
    length: float = 0.2, width: float = 0.2, height: float = 0.3,
    score: float = 1.0,
) -> dict:
    values = [0.0] * len(ACTION_NAMES)
    for name, value in (
        ("container_index", container), ("command_x", x), ("command_y", y),
        ("length", length), ("width", width), ("height", height),
        ("immediate_score", score),
    ):
        values[ACTION_NAMES.index(name)] = value
    return {"feature_names": list(ACTION_NAMES), "values": values}


def _state() -> dict:
    return {
        "container_features": [
            "length", "width", "height", "cut_x", "cut_y", "thickness",
            "buffer", "has_shelf", "is_priority_dedicated",
        ],
        "container_values": [
            [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ],
        "packed_item_features": [
            "container_index", "local_x", "local_y", "local_z",
            "quaternion_x", "quaternion_y", "quaternion_z", "quaternion_w",
            "length", "width", "height",
        ],
        "packed_item_values": [],
    }


class DistributionalFillPreactionV6Tests(unittest.TestCase):
    def test_stamp_raises_footprint_cells_to_rest_top(self) -> None:
        source = [0.0] * (2 * GRID_SIZE * GRID_SIZE)
        stamped, rest_top = _stamped_grid(
            source, _state(), _action(x=-0.375, y=-0.375, height=0.3)
        )
        self.assertAlmostEqual(rest_top, 0.3)
        self.assertAlmostEqual(stamped[0], 0.3)
        self.assertAlmostEqual(sum(stamped), 0.3)

    def test_stamp_drops_onto_highest_cell_under_footprint(self) -> None:
        source = [0.0] * (2 * GRID_SIZE * GRID_SIZE)
        source[0] = 0.5
        stamped, rest_top = _stamped_grid(
            source, _state(),
            _action(x=-0.25, y=-0.375, length=0.45, height=0.3),
        )
        self.assertAlmostEqual(rest_top, 0.8)
        self.assertAlmostEqual(stamped[0], 0.8)
        self.assertAlmostEqual(stamped[GRID_SIZE], 0.8)

    def test_second_container_stamp_leaves_first_untouched(self) -> None:
        source = [0.0] * (2 * GRID_SIZE * GRID_SIZE)
        stamped, _ = _stamped_grid(
            source, _state(), _action(container=1.0, x=-0.375, y=-0.375)
        )
        self.assertAlmostEqual(sum(stamped[:GRID_SIZE * GRID_SIZE]), 0.0)
        self.assertGreater(sum(stamped[GRID_SIZE * GRID_SIZE:]), 0.0)

    def test_pair_vector_excludes_immediate_score_from_grid_terms(self) -> None:
        row = {
            "source_state_tensor": _state(),
            "lower_action_tensor": _action(x=-0.375, y=-0.375, score=1.0),
            "higher_action_tensor": _action(x=0.375, y=0.375, score=9.0),
        }
        vector = grid_pair_vector(row)
        action_delta_length = len(ACTION_NAMES) - 1
        self.assertEqual(
            len(vector), action_delta_length + 2 * GRID_SIZE * GRID_SIZE + 4
        )
        self.assertAlmostEqual(vector[action_delta_length + 0], -0.3)
        self.assertAlmostEqual(
            vector[action_delta_length + 2 * GRID_SIZE * GRID_SIZE], 0.0
        )


if __name__ == "__main__":
    unittest.main()
