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




class FastActionCenterTests(unittest.TestCase):
    def test_action_center_agrees_with_reference(self):
        rng = random.Random(1)
        for board, slow, scene in _boards():
            fast = dataclasses.replace(slow, fast_validate=True)
            for idx in range(len(board.containers)):
                model = board.model(idx)
                container = board.container(idx)
                tops = [model.z_floor] + [float(s.maximum[2]) for s in model.shelves]
                tops += [float(p.box.maximum[2]) for p in board.placements[idx]]
                for _ in range(300):
                    size = (rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4))
                    z = rng.choice(tops) + size[2] / 2.0 + rng.choice((0.0, 0.0, 0.0, 0.004, -0.004, 0.03))
                    box = AABB((rng.uniform(-0.9, 0.9), rng.uniform(-0.7, 0.7), z), size, "probe")
                    ref = layer1.action_center(box, model, container, slow)
                    got = layer1.action_center(box, model, container, fast)
                    self.assertEqual([float(v) for v in ref], [float(v) for v in got], (scene.name, idx, box))




class ContactPatchTests(unittest.TestCase):
    def test_contact_patches_agree_with_reference(self):
        from rule_alpha import stability

        rng = random.Random(2)
        for board, slow, scene in _boards():
            for idx in range(len(board.containers)):
                model = board.model(idx)
                container = board.container(idx)
                tops = [model.z_floor] + [float(s.maximum[2]) for s in model.shelves]
                tops += [float(p.box.maximum[2]) for p in board.placements[idx]]
                for _ in range(300):
                    size = (rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4))
                    z = rng.choice(tops) + size[2] / 2.0 + rng.choice((0.0, 0.0, 0.0, 0.004, -0.004, 0.03))
                    box = AABB((rng.uniform(-0.9, 0.9), rng.uniform(-0.7, 0.7), z), size, "probe")
                    for flags in ((False, False), (True, False), (True, True)):
                        ref = stability._contact_patches_reference(box, container, slow.contact_tolerance, *flags)
                        got = stability.contact_patches(box, container, slow.contact_tolerance, *flags)
                        self.assertEqual(got, ref, (scene.name, idx, box, flags))




class ContactFeatureTests(unittest.TestCase):
    def test_wall_and_item_contact_agree_with_reference(self):
        rng = random.Random(3)
        for board, slow, scene in _boards():
            for idx in range(len(board.containers)):
                model = board.model(idx)
                container = board.container(idx)
                tops = [model.z_floor] + [float(p.box.maximum[2]) for p in board.placements[idx]]
                for _ in range(300):
                    size = (rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4))
                    z = rng.choice(tops) + size[2] / 2.0 + rng.choice((0.0, 0.0, 0.02, -0.02, 0.1))
                    box = AABB((rng.uniform(-0.9, 0.9), rng.uniform(-0.7, 0.7), z), size, "probe")
                    self.assertEqual(layer1._wall_contact(box, model, container, slow),
                                     layer1._wall_contact_reference(box, model, container, slow), (scene.name, box))
                    self.assertEqual(layer1._item_contact(box, container, slow),
                                     layer1._item_contact_reference(box, container, slow), (scene.name, box))


if __name__ == "__main__":
    unittest.main()


class ValidatePointsTests(unittest.TestCase):
    """``fastgeom.validate_points`` gives ``validate``'s verdict for every point."""

    def _grids(self, rng, model, board, idx):
        tops = [model.z_floor] + [float(s.maximum[2]) for s in model.shelves]
        tops += [float(p.box.maximum[2]) for p in board.placements[idx]]
        for _ in range(12):
            size = (rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4))
            z = rng.choice(tops) + size[2] / 2.0 + rng.choice((0.0, 0.0, 0.0, 0.03, -0.01, 0.0005))
            pts = [(rng.uniform(-0.95, 0.95), rng.uniform(-0.75, 0.75)) for _ in range(40)]
            # anchors on packed edges too, where the clearances bite
            for p in board.placements[idx][:6]:
                pts.append((float(p.box.maximum[0]) + size[0] / 2.0 + 0.02, float(p.box.center[1])))
                pts.append((float(p.box.minimum[0]) + size[0] / 2.0, float(p.box.minimum[1]) + size[1] / 2.0))
            yield pts, z, size

    def test_agrees_with_validate(self):
        from rule_alpha import stability

        rng = random.Random(1)
        checked = accepted = 0
        for board, slow, scene in _boards():
            for conservative in (False, True):
                for band in (0.0, 0.01):
                    cfg = dataclasses.replace(slow, fast_validate=True, conservative_transport=conservative, band_lift=band)
                    for idx in range(len(board.containers)):
                        model = board.model(idx)
                        container = board.container(idx)
                        for pts, z, size in self._grids(rng, model, board, idx):
                            got = fastgeom.validate_points(pts, z, size, model, container, cfg, stability.is_stable)
                            self.assertEqual(len(got), len(pts))
                            for (x, y), verdict in zip(pts, got):
                                ref = layer1.validate(AABB((x, y, z), size, "probe"), model, container, cfg)
                                self.assertEqual(verdict, ref[0], (scene.name, idx, conservative, band, (x, y, z), size, ref))
                                checked += 1
                                accepted += int(ref[0])
        self.assertGreater(checked, 3000)
        self.assertGreater(accepted, 30)

    def test_empty_grid(self):
        from rule_alpha import stability

        board, slow, _scene = _boards()[0]
        self.assertEqual(fastgeom.validate_points([], 0.3, (0.5, 0.4, 0.2), board.model(0), board.container(0),
                                                  slow, stability.is_stable), [])


class DropHeightTests(unittest.TestCase):
    def test_vectorised_drop_height_agrees_with_the_loop(self):
        from rule_alpha import planner

        rng = random.Random(2)
        for board, slow, _scene in _boards():
            for idx in range(len(board.containers)):
                model = board.model(idx)
                container = board.container(idx)
                for _ in range(200):
                    x, y = rng.uniform(-0.95, 0.95), rng.uniform(-0.75, 0.75)
                    dx, dy, dz = rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4)
                    planner._drop_height._vectorised = False
                    try:
                        ref = planner._drop_height(container, model, x, y, dx, dy, dz)
                    finally:
                        planner._drop_height._vectorised = True
                    self.assertEqual(planner._drop_height(container, model, x, y, dx, dy, dz), ref)


class EvaluatePointsTests(unittest.TestCase):
    def test_agrees_with_evaluate(self):
        from rule_alpha import stability

        rng = random.Random(3)
        checked = supported = 0
        for board, slow, _scene in _boards():
            for prio, soft in ((False, False), (True, True)):
                cfg = dataclasses.replace(slow, priority_is_structure=prio, soft_is_structure=soft)
                for idx in range(len(board.containers)):
                    model = board.model(idx)
                    container = board.container(idx)
                    tops = [model.z_floor] + [float(s.maximum[2]) for s in model.shelves]
                    tops += [float(p.box.maximum[2]) for p in board.placements[idx]]
                    for _ in range(10):
                        size = (rng.uniform(0.3, 0.75), rng.uniform(0.25, 0.56), rng.uniform(0.2, 0.4))
                        z = rng.choice(tops) + size[2] / 2.0 + rng.choice((0.0, 0.0, 0.0, 0.004, -0.004))
                        pts = [(rng.uniform(-0.95, 0.95), rng.uniform(-0.75, 0.75)) for _ in range(30)]
                        for p in board.placements[idx][:6]:
                            pts.append((float(p.box.center[0]) + 0.1, float(p.box.center[1]) - 0.05))
                        got = stability.evaluate_points([x for x, _y in pts], [y for _x, y in pts], z, size, container, cfg)
                        for (x, y), state in zip(pts, got):
                            ref = stability.evaluate(AABB((x, y, z), size, "probe"), container, cfg)
                            self.assertEqual((state.margin, state.contact_area, state.contact_count, state.polygon),
                                             (ref.margin, ref.contact_area, ref.contact_count, ref.polygon), (x, y, z, size))
                            checked += 1
                            supported += int(ref.contact_count > 0)
        self.assertGreater(checked, 1000)
        self.assertGreater(supported, 100)
