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


if __name__ == "__main__":
    unittest.main()
