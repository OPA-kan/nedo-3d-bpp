"""The count mode's switch: the candidate generator skips the cover vetoes
only when ``allow_cover_other_attribute`` is set."""

from __future__ import annotations

import dataclasses
import unittest

from bench.scenes import make_scene
from rule_alpha import classify as cls
from rule_alpha import layer1
from rule_alpha.config import DEFAULT_CONFIG
from wedge_rl.stack import stack_candidates

BASE = {"index": 1, "length": 0.75, "width": 0.56, "height": 0.27, "mass": 8.0,
        "is_soft": False, "is_prioritized": True}
ITEM = {"index": 7, "length": 0.4, "width": 0.3, "height": 0.25, "mass": 5.0,
        "is_soft": False, "is_prioritized": False}


class CountModeTests(unittest.TestCase):
    def setUp(self):
        self.config = dataclasses.replace(
            DEFAULT_CONFIG, no_cover_other_attribute=True, priority_is_structure=True,
            conservative_transport=False, routing_any_container=True, stack_max_bottom=10.0,
        )
        containers = make_scene(1, "c1", "C").rule_alpha_containers()
        thickness = float(containers[0]["thickness"])
        base = dict(BASE, pos=(0.3, 0.2, thickness + BASE["height"] / 2.0), orn=(0.0, 0.0, 0.0, 1.0))
        containers[0]["packed_items"].append(base)
        self.containers = containers
        self.top = thickness + BASE["height"]

    def _on_the_priority_box(self, config) -> int:
        board = layer1.Board(self.containers, config)
        profile = cls.classify_item(ITEM["index"], ITEM, config)
        cands = stack_candidates(board.model(0), board.container(0), config, profile,
                                 max_candidates=400, mass=5.0, tower_min=None, dense=0.04)
        self.assertTrue(cands, "the floor alone should give candidates")
        return sum(1 for c in cands if abs(c.bottom - self.top) < 0.01)

    def test_cover_rule_keeps_normal_cargo_off_priority_cargo(self):
        self.assertEqual(self._on_the_priority_box(self.config), 0)

    def test_count_pass_lets_the_physics_judge(self):
        config = dataclasses.replace(self.config, allow_cover_other_attribute=True)
        self.assertGreater(self._on_the_priority_box(config), 0)


if __name__ == "__main__":
    unittest.main()
