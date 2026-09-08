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
            gain = cands[a].gain if a != PASS else 0.0
            _obs, r, _d, _i = env.step(a)
            self.assertAlmostEqual(r, gain)
            total += r
        self.assertAlmostEqual(total, env.strip_volume())
        for c in env.placed:
            self.assertGreaterEqual(c.gain, 0.0)
            self.assertLessEqual(c.gain, float(np.prod(c.dims)) + 1e-9)

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

    def test_option_places_hard_items_and_leaves_soft_to_the_ladder(self):
        """Inside rule-alpha: the option proposes a strip placement for a hard
        item on an empty board (a floor base is always legal and the trained
        policy takes one), declines soft cargo, and the agent's action carries
        the proposed pose."""
        import pathlib

        from bench.arms import make_arm
        from bench.scenes import make_scene
        from rule_alpha import classify as cls
        from wedge_rl.option import ARCHETYPE, WedgeOption

        policy_dir = pathlib.Path("reports/wedge/ppo-c1-s0")
        if not (policy_dir / "policy.pt").exists():
            self.skipTest("no trained wedge policy in the tree")
        config = make_arm("ladder-stable").config
        scene = make_scene(1, "c1", "C")
        board = layer1.Board(scene.rule_alpha_containers(), config)
        option = WedgeOption(policy_dir, config)
        hard = cls.classify_item(0, {"index": 0, "length": 0.55, "width": 0.40, "height": 0.24,
                                     "mass": 8, "is_soft": False, "is_prioritized": False}, config)
        soft = cls.classify_item(1, {"index": 1, "length": 0.50, "width": 0.40, "height": 0.40,
                                     "mass": 10, "is_soft": True, "is_prioritized": False}, config)
        self.assertIsNone(option.propose(board, soft))
        decision = option.propose(board, hard)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.placement.archetype, ARCHETYPE)
        ok, why = layer1.validate(decision.placement.box, board.model(0), board.container(0), config)
        self.assertTrue(ok, why)
        arm = make_arm(f"wedge:{policy_dir}")
        agent = arm(scene)
        agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        action = agent.policy({"container_list": scene.rule_alpha_containers(), "pool_list": [hard.item]})
        self.assertEqual(action["item_idx"], 0)
        self.assertEqual(agent.last_decision.placement.archetype, ARCHETYPE)
        self.assertTrue(np.allclose(action["place_pos"][:2], decision.placement.box.center[:2], atol=1e-6))

    def test_shelf_candidates_sit_on_the_shelf_and_pay_their_volume(self):
        from wedge_rl.shelf import ShelfEnv

        env = ShelfEnv("c1s", n_items=8)
        env.reset(2)
        checked = 0
        total = 0.0
        while not env.done:
            cands = env.candidates()
            for c in cands:
                ok, why = layer1.validate(c.box, env.model, env.container, env.config)
                self.assertTrue(ok, why)
                self.assertGreaterEqual(float(c.box.minimum[2]), env.shelf_top - 1e-6)
                self.assertGreaterEqual(float(c.box.minimum[0]), env.rect.x_min - 1e-6)
                self.assertLessEqual(float(c.box.maximum[1]), env.rect.y_max + 1e-6)
                self.assertAlmostEqual(c.gain, float(np.prod(c.dims)))
                checked += 1
            a = staircase(env)
            gain = cands[a].gain if a != PASS else 0.0
            _obs, r, _d, _i = env.step(a)
            self.assertAlmostEqual(r, gain)
            total += r
        self.assertGreater(checked, 10)
        self.assertGreater(total, 0.0)
        self.assertAlmostEqual(total, env.gain_total())
        obs = env.observation()
        self.assertEqual(obs["heightmap"].shape, (env.nx, env.ny))
        self.assertEqual(obs["profile"].shape, (env.nx,))

    def test_parallel_collection_matches_single_process(self):
        """Forked workers play the same seeds to the same trajectories."""
        import torch

        from wedge_rl.ppo import Collector, Policy
        from wedge_rl.regions import env_factory

        factory = env_factory("wedge", "c1", 4)
        env = factory()
        torch.manual_seed(0)
        policy = Policy(env.nx, env.ny)
        single = Collector(factory, env.nx, env.ny, workers=1)
        multi = Collector(factory, env.nx, env.ny, workers=2)
        try:
            torch.manual_seed(1); s_steps, s_ret = single.collect(policy, 4, seed_base=500)
            torch.manual_seed(1); m_steps, m_ret = multi.collect(policy, 4, seed_base=500)
        finally:
            multi.close()
        self.assertEqual(len(s_steps), len(m_steps))
        self.assertEqual(sorted(round(r, 9) for r in s_ret), sorted(round(r, 9) for r in m_ret))

    def test_beam_search_actions_replay_to_the_reported_gain(self):
        from wedge_rl.baselines import staircase as roll
        from wedge_rl.search import beam_search

        env = WedgeEnv("c1", n_items=4)
        result = beam_search(env, 7, width=4, k=3, spread=2, rollout=roll)
        self.assertEqual(len(result["actions"]), 4)
        env.reset(7)
        total = 0.0
        for a in result["actions"]:
            cands = env.candidates()
            if a != PASS:
                self.assertLess(a, len(cands))
            _obs, r, _d, _i = env.step(a)
            total += r
        self.assertAlmostEqual(total, result["gain"])
        self.assertEqual(len(env.placed), result["placed"])

    def test_teacher_trajectory_and_behaviour_cloning(self):
        """The searched actions replay to the searched gain, and cloning a
        handful of them makes the policy reproduce them."""
        import torch

        from wedge_rl.baselines import greedy_any as roll
        from wedge_rl.ppo import Policy, pretrain, teacher_accuracy
        from wedge_rl.search import beam_search, teacher_trajectory
        from wedge_rl.shelf import ShelfEnv

        env = ShelfEnv("c1s", n_items=4)
        steps = []
        for seed in (11, 12):
            result = beam_search(env, seed, width=3, k=3, spread=2, rollout=roll)
            traj = teacher_trajectory(env, seed, result["actions"])
            self.assertEqual(len(traj), 4)
            self.assertAlmostEqual(sum(s["r"] for s in traj), result["gain"])
            steps.extend(traj)
        torch.manual_seed(0)
        policy = Policy(env.nx, env.ny)
        before = teacher_accuracy(policy, steps)
        pretrain(policy, steps, epochs=60, lr=3e-3, log=None)
        after = teacher_accuracy(policy, steps)
        self.assertGreaterEqual(after, max(before, 0.75))

    def test_gp_expressions_evaluate_and_evolve(self):
        import random as _random

        from wedge_rl import gp
        from wedge_rl.regions import env_factory

        rng = _random.Random(0)
        feats = np.random.default_rng(0).random((5, 12)).astype(np.float32)
        state = np.zeros(5, dtype=np.float32)
        for _ in range(50):
            tree = gp.random_tree(rng, 5)
            vals = gp.evaluate(tree, feats, state)
            self.assertEqual(vals.shape, (5,))
            self.assertTrue(np.all(np.isfinite(vals)), str(tree))
            child = gp.crossover(rng, tree, gp.random_tree(rng, 4), 6)
            self.assertLessEqual(child.depth(), 6)
            mutant = gp.mutate(rng, tree, 6)
            self.assertLessEqual(mutant.depth(), 6)
            self.assertEqual(str(gp.Node.from_json(tree.to_json())), str(tree))
        # the 'gain' expression is greedy_gain: same gains on the wedge
        env = WedgeEnv("c1", n_items=5)
        from wedge_rl.baselines import greedy_gain
        for seed in (1, 2):
            a = run_episode(env, gp.policy_of(gp.Node("gain")), seed)["gain"]
            b = run_episode(env, greedy_gain, seed)["gain"]
            self.assertAlmostEqual(a, b)
        result = gp.evolve(env_factory("wedge", "c1", 4), [3, 4], generations=2, population=6, log=None)
        self.assertIsNotNone(result["best"])
        self.assertEqual(len(result["history"]), 2)

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
