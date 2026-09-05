"""The vectorised validate must give the reference's verdict on every box."""

from __future__ import annotations

import dataclasses
import random
import unittest

from bench.arms import make_arm
from bench.scenes import make_scene
from rule_alpha import fastgeom, layer1
from rule_alpha._reuse import AABB
from rule_alpha.config import DEFAULT_CONFIG


def _boards():
    """A few mid-episode boards, built with the reference validate."""
    slow = dataclasses.replace(DEFAULT_CONFIG, fast_validate=False)
    out = []
    for seed, layout in ((3, "c1s"), (5, "c2p")):
        scene = make_scene(seed, layout, "C", items_per_container=14)
        arm = make_arm("ladder-stable")
        arm.config = dataclasses.replace(arm.config, fast_validate=False)
        containers = scene.rule_alpha_containers()
        agent = arm(scene)
        agent.get_init_states({"optimize": False, "lookahead_k": 1, "container_list": containers})
        board = layer1.Board(containers, slow)
        for item in scene.items[:10]:
            action = agent.policy({"optimize": False, "lookahead_k": 1,
                                   "container_list": board.containers, "pool_list": [item]})
            if action is None:
                break
            board.apply(agent.last_decision.placement)
        out.append((board, slow, scene))
    return out


class FastValidateTests(unittest.TestCase):
    def test_agrees_with_reference_on_random_boxes(self):
        rng = random.Random(0)
        checked = accepted = 0
        for board, slow, scene in _boards():
            fast = dataclasses.replace(slow, fast_validate=True)
            for idx in range(len(board.containers)):
                model = board.model(idx)
                container = board.container(idx)
                for _ in range(400):
                    size = (rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4))
                    # bias towards resting poses: floor, shelf, or a packed top
                    tops = [model.z_floor] + [float(s.maximum[2]) for s in model.shelves]
                    tops += [float(p.box.maximum[2]) for p in board.placements[idx]]
                    z = rng.choice(tops) + size[2] / 2.0 + rng.choice((0.0, 0.0, 0.0, 0.03, -0.01))
                    box = AABB((rng.uniform(-0.9, 0.9), rng.uniform(-0.7, 0.7), z), size, "probe")
                    ref = layer1._validate_reference(box, model, container, slow)
                    got = layer1.validate(box, model, container, fast)
                    self.assertEqual(got, ref, (scene.name, idx, box))
                    checked += 1
                    accepted += int(ref[0])
        self.assertGreater(checked, 1000)
        self.assertGreater(accepted, 20)   # the sample has to contain accepts too

    def test_agrees_on_the_planner_own_candidates(self):
        for board, slow, scene in _boards():
            fast = dataclasses.replace(slow, fast_validate=True)
            for idx in range(len(board.containers)):
                model = board.model(idx)
                container = board.container(idx)
                for placement in board.placements[idx]:
                    ref = layer1._validate_reference(placement.box, model, container, slow)
                    got = layer1.validate(placement.box, model, container, fast)
                    self.assertEqual(got, ref)

    def test_cache_invalidates_when_an_item_is_added(self):
        scene = make_scene(1, "c1", "C")
        c = scene.rule_alpha_containers()[0]
        before = fastgeom.obstacles(c)["packed_min"].shape[0]
        c["packed_items"].append({"index": 0, "length": 0.5, "width": 0.4, "height": 0.2,
                                  "is_soft": False, "is_prioritized": False,
                                  "pos": (0.0, 0.0, 0.15), "dims": (0.5, 0.4, 0.2)})
        after = fastgeom.obstacles(c)["packed_min"].shape[0]
        self.assertEqual((before, after), (0, 1))


if __name__ == "__main__":
    unittest.main()
