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



@unittest.skipUnless(shadow.available(), "pybullet is not installed")
class ShadowGateTests(unittest.TestCase):
    def test_agent_checks_every_decision(self):
        import dataclasses

        from bench.arms import make_arm

        scene = make_scene(2, "c1", "C", items_per_container=8)
        arm = make_arm("ladder-stable")
        arm.config = dataclasses.replace(arm.config, shadow_check=True)
        containers = scene.rule_alpha_containers()
        agent = arm(scene)
        agent.get_init_states({"optimize": False, "lookahead_k": 1, "container_list": containers})
        placed = 0
        for item in scene.items[:4]:
            obs = {"optimize": False, "lookahead_k": 1, "container_list": containers, "pool_list": [item]}
            action = agent.policy(obs)
            if action is None:
                break
            placed += 1
            self.assertIsNotNone(agent.last_shadow)
            self.assertIn(agent.last_shadow["outcome"], ("kept", "replaced", "kept-after-veto", "fallback-after-veto"))
            # the placed box joins the world at its target pose (the
            # analytic board's view; the settled pose is what the
            # simulator would report)
            pos = [float(v) for v in action["place_pos"]]
            packed = dict(item, pos=pos, orn=list(shadow.p.getQuaternionFromEuler(shadow.ORNS[int(action["orientation"])])),
                          orientation=int(action["orientation"]))
            containers[int(action["container_idx"])]["packed_items"].append(packed)
        self.assertGreaterEqual(placed, 3)
        self.assertGreaterEqual(agent.shadow_stats["checks"], placed)
        self.assertEqual(agent.shadow_stats["vetoes"], agent.shadow_stats["replaced"]
                         + agent.shadow_stats.get("kept_soft", 0) + agent.shadow_stats.get("continued", 0))


if __name__ == "__main__":
    unittest.main()
