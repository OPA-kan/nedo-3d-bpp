"""The chamfer-strip environment."""

from __future__ import annotations

import random
import unittest

import numpy as np

from rule_alpha import layer1
from wedge_rl.baselines import run_episode, staircase
from wedge_rl.env import PASS, WedgeEnv


class WedgeEnvTests(unittest.TestCase):
    def test_reset_is_deterministic(self):
        env = WedgeEnv("c1", n_items=6)
        a = [i["sku"] for i in env.reset(3) and env.stream]
        b = [i["sku"] for i in env.reset(3) and env.stream]
        self.assertEqual(a, b)

    def test_every_candidate_is_valid_and_in_the_play_region(self):
        env = WedgeEnv("c1", n_items=6)
        env.reset(1)
        checked = 0
        while not env.done:
            for c in env.candidates():
                ok, why = layer1.validate(c.box, env.model, env.container, env.config)
                self.assertTrue(ok, why)
                self.assertLessEqual(float(c.box.maximum[0]), env.x_max_play + 1e-9)
                self.assertLessEqual(float(c.box.maximum[2]), env.z_top + 1e-9)
                checked += 1
            env.step(staircase(env))
        self.assertGreater(checked, 10)

    def test_reward_is_the_volume_left_of_the_floor_line(self):
        env = WedgeEnv("c1", n_items=8)
        env.reset(3)
        total = 0.0
        while not env.done:
            a = staircase(env)
            cands = env.candidates()
            gain = cands[a].strip_gain if a != PASS else 0.0
            _obs, r, _d, _i = env.step(a)
            self.assertAlmostEqual(r, gain)
            total += r
        self.assertAlmostEqual(total, env.strip_volume())
        for c in env.placed:
            self.assertGreaterEqual(c.strip_gain, 0.0)
            self.assertLessEqual(c.strip_gain, float(np.prod(c.dims)) + 1e-9)

    def test_pass_places_nothing(self):
        env = WedgeEnv("c1", n_items=3)
        env.reset(0)
        _obs, r, done, info = env.step(PASS)
        self.assertEqual((r, info["passed"], len(env.placed)), (0.0, True, 0))
        self.assertFalse(done)

    def test_staircase_recovers_some_wedge(self):
        env = WedgeEnv("c1", n_items=14)
        res = [run_episode(env, staircase, s, random.Random(s)) for s in range(6)]
        self.assertGreater(max(r["strip_volume"] for r in res), 0.0)

    def test_replay_scene_and_scripted_actions(self):
        """The replay scene carries exactly the placed boxes, and the scripted
        agent commands each planned pose (without running PyBullet)."""
        from wedge_rl.replay import ScriptedAgent, arrangement, scene_for

        env = WedgeEnv("c1", n_items=10)
        placed = arrangement(env, staircase, 3)
        self.assertGreater(len(placed), 0)
        scene = scene_for(placed, "c1", 3)
        self.assertEqual([i["index"] for i in scene.items], list(range(len(placed))))
        for (item, _c), spec in zip(placed, scene.items):
            self.assertEqual((spec["length"], spec["width"], spec["height"]),
                             (item["length"], item["width"], item["height"]))
            self.assertIn("lateralFriction", spec)
        plan = {i: c for i, (_it, c) in enumerate(placed)}
        agent = ScriptedAgent(plan, env.config)
        observation = {"container_list": scene.rule_alpha_containers(), "pool_list": [scene.items[0]]}
        action = agent.policy(observation)
        self.assertEqual(action["item_idx"], 0)
        self.assertEqual(action["orientation"], plan[0].orientation)
        self.assertTrue(np.allclose(action["place_pos"][:2], plan[0].box.center[:2], atol=1e-6))
        self.assertGreaterEqual(float(action["place_pos"][2]), float(plan[0].box.center[2]))
        self.assertIsNone(agent.policy({"container_list": observation["container_list"],
                                        "pool_list": [{"index": 99}]}))


if __name__ == "__main__":
    unittest.main()
