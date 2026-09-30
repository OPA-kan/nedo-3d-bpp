"""The shadow world gives the simulator's verdicts on simple poses."""

from __future__ import annotations

import unittest

from bench.scenes import make_scene
from rule_alpha import shadow

ITEM = {"index": 7, "length": 0.4, "width": 0.3, "height": 0.25, "mass": 5.0, "is_soft": False}


@unittest.skipUnless(shadow.available(), "pybullet is not installed")
class ShadowSimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = shadow.ShadowSim()
        cls.containers = make_scene(1, "c1", "C").rule_alpha_containers()
        cls.thickness = float(cls.containers[0]["thickness"])
        cls.width = float(cls.containers[0]["width"])

    def test_floor_pose_settles_in_place(self):
        self.sim.sync(self.containers)
        out = self.sim.check(0, ITEM, (0.2, 0.0, self.thickness + 0.125), 0)
        self.assertTrue(out["transport_ok"])
        self.assertTrue(out["settle_ok"])
        self.assertLess(out["drift"], 0.005)
        self.assertLess(out["angle_deg"], 1.0)

    def test_floating_pose_drops_to_the_floor(self):
        self.sim.sync(self.containers)
        out = self.sim.check(0, ITEM, (0.2, 0.0, self.thickness + 0.125 + 0.15), 0)
        self.assertTrue(out["transport_ok"])
        self.assertTrue(out["settle_ok"])  # 0.15 m is under the 0.3 m limit
        self.assertAlmostEqual(out["drift"], 0.15, delta=0.02)
        self.assertAlmostEqual(out["settled_local"][2], self.thickness + 0.125, delta=0.01)

    def test_far_drop_fails_the_settle(self):
        self.sim.sync(self.containers)
        out = self.sim.check(0, ITEM, (0.2, 0.0, self.thickness + 0.125 + 0.5), 0)
        self.assertTrue(out["transport_ok"])
        self.assertFalse(out["settle_ok"])
        self.assertGreater(out["drift"], 0.3)

    def test_item_in_the_sweep_path_fails_the_transport(self):
        containers = [dict(c) for c in self.containers]
        blocker = dict(ITEM, index=1, pos=(0.2, -self.width / 2.0 + 0.3, self.thickness + 0.125),
                       orn=(0.0, 0.0, 0.0, 1.0))
        containers[0] = dict(containers[0], packed_items=[blocker])
        self.sim.sync(containers)
        out = self.sim.check(0, ITEM, (0.2, 0.1, self.thickness + 0.125), 0)
        self.assertFalse(out["transport_ok"])
        # the same pose clears once the blocker is gone
        self.sim.sync(self.containers)
        self.assertTrue(self.sim.check(0, ITEM, (0.2, 0.1, self.thickness + 0.125), 0)["transport_ok"])

    def test_stacked_pose_rests_on_the_packed_item(self):
        containers = [dict(c) for c in self.containers]
        base = dict(ITEM, index=1, pos=(0.2, 0.1, self.thickness + 0.125), orn=(0.0, 0.0, 0.0, 1.0))
        containers[0] = dict(containers[0], packed_items=[base])
        self.sim.sync(containers)
        out = self.sim.check(0, ITEM, (0.2, 0.1, self.thickness + 0.25 + 0.125), 0)
        self.assertTrue(out["transport_ok"])
        self.assertTrue(out["settle_ok"])
        self.assertLess(out["drift"], 0.01)


if __name__ == "__main__":
    unittest.main()
