"""Tests for the measurement bench that do not need PyBullet."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import numpy as np

from bench import compare
from bench.agreement import confusion
from bench.arms import config_from_spec, make_arm
from bench.metrics import COMPARED, attribute_violations
from bench.scenes import LAYOUTS, SKUS, SUITES, build_suite, make_scene


class SceneTests(unittest.TestCase):
    def test_same_seed_same_scene(self):
        a = make_scene(7, "c2p", "B")
        b = make_scene(7, "c2p", "B")
        self.assertEqual(a.items, b.items)
        self.assertEqual(a.containers, b.containers)
        self.assertEqual(a.name, "b-c2p-s0007")

    def test_different_seed_different_stream(self):
        self.assertNotEqual(make_scene(1, "c1").items, make_scene(2, "c1").items)

    def test_task_shapes_follow_the_official_flow(self):
        self.assertTrue(make_scene(1, "c1", "A").optimize)
        self.assertFalse(make_scene(1, "c1", "B").optimize)
        self.assertFalse(make_scene(1, "c1", "C").optimize)
        self.assertEqual(make_scene(1, "c1", "B").look_ahead, 10)
        self.assertEqual(make_scene(1, "c1", "C").look_ahead, 1)
        config = make_scene(1, "c1", "B").sim_config()
        self.assertEqual(config["item_stream"]["max_space"], 1)
        self.assertEqual(config["validator"]["inclusion_margin"], -0.005)

    def test_items_are_official_skus(self):
        dims = {(s[1], s[2], s[3], s[4], s[5]) for s in SKUS}
        for item in make_scene(3, "c2").items:
            self.assertIn(
                (item["length"], item["width"], item["height"], item["mass"], item["is_soft"]),
                dims,
            )
        self.assertEqual(len(make_scene(3, "c2").items), 82)

    def test_layouts_and_suites(self):
        self.assertEqual(len(LAYOUTS["c2p"]), 2)
        self.assertTrue(make_scene(1, "c2p").containers[0]["is_prioritized"])
        self.assertEqual(len(build_suite("smoke")), 4)
        self.assertEqual(len(build_suite("core")), len(SUITES["core"]))
        names = [s.name for s in build_suite("core")]
        self.assertEqual(len(names), len(set(names)))

    def test_rule_alpha_containers_carry_offsets(self):
        scene = make_scene(1, "c2")
        containers = scene.rule_alpha_containers()
        self.assertEqual(len(containers), 2)
        self.assertEqual(containers[1]["_spec"]["index"], 1)


class ArmTests(unittest.TestCase):
    def test_override_parsing(self):
        config = config_from_spec("ladder@layer2_family_quota=48,seal_ranks_terraces=true")
        self.assertEqual(config.layer2_family_quota, 48)
        self.assertTrue(config.seal_ranks_terraces)
        with self.assertRaises(KeyError):
            config_from_spec("ladder@no_such_field=1")
        with self.assertRaises(KeyError):
            make_arm("random")

    def test_search_arm_parses_imagined_futures_and_runs(self):
        from bench.analytic import run_analytic_episode

        arm = make_arm("search:3/2/4+ladder-stable")
        self.assertEqual((arm.k, arm.streams, arm.horizon), (3, 2, 4))
        self.assertEqual(make_arm("search:6+ladder-stable").streams, 0)
        scene = make_scene(7, "c1", "C", items_per_container=5)
        record = run_analytic_episode(scene, arm)
        self.assertEqual(record["metrics"]["placed_count"], record["metrics"]["attempted"])
        # the same scene gives the same placements: the imagined futures are seeded
        again = run_analytic_episode(scene, arm)
        self.assertEqual([s.get("place_pos") for s in record["steps"]],
                         [s.get("place_pos") for s in again["steps"]])

    def test_offline_dry_run_defers_what_the_core_declines(self):
        from bench.analytic import run_analytic_episode

        scene = make_scene(11, "c1", "A", items_per_container=6)
        # an item no container can take, first in every rule-based order
        big = dict(scene.items[0])
        big.update({"index": 900, "length": 3.5, "width": 3.5, "height": 0.4, "mass": 30.0,
                    "is_soft": False, "is_prioritized": False})
        scene.items.insert(0, big)
        plain = run_analytic_episode(scene, make_arm("ladder-stable"))
        dry = run_analytic_episode(scene, make_arm("ladder-stable@offline_dry_run=true,offline_budget_seconds=60"))
        self.assertEqual(dry["order"][-1], 900)
        self.assertGreater(dry["metrics"]["placed_count"], plain["metrics"]["placed_count"])
        self.assertEqual(plain["metrics"]["end_reason"], "declined")

    def test_last_resort_only_adds_placements_where_the_ladder_declined(self):
        from bench.analytic import run_analytic_episode

        scene = make_scene(13, "c1", "C", items_per_container=24)
        strict = run_analytic_episode(scene, make_arm("ladder-stable"))
        relaxed = run_analytic_episode(scene, make_arm("ladder-stable@last_resort_relax=true"))
        n = strict["metrics"]["placed_count"]
        # the same placements up to the strict run's decline, then possibly more
        self.assertEqual([s.get("place_pos") for s in strict["steps"][:n]],
                         [s.get("place_pos") for s in relaxed["steps"][:n]])
        self.assertGreaterEqual(relaxed["metrics"]["placed_count"], n)
        self.assertIn(relaxed["metrics"]["end_reason"], ("declined", "stream-exhausted"))

    def test_submission_agent_never_answers_none(self):
        import importlib.util
        import pathlib

        path = pathlib.Path("submission/agent.py").resolve()
        spec = importlib.util.spec_from_file_location("_submission_agent", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        agent = module.Agent(str(path.parent))
        scene = make_scene(3, "c1", "C", items_per_container=3)
        containers = scene.rule_alpha_containers()
        agent.get_init_states({"container_list": containers})
        big = {"index": 7, "length": 3.5, "width": 3.5, "height": 0.4, "mass": 30.0,
               "is_soft": False, "is_prioritized": False}
        action = agent.policy({"container_list": containers, "pool_list": [big]})
        self.assertEqual(set(action), {"item_idx", "container_idx", "place_pos", "orientation"})
        self.assertEqual(len(action["place_pos"]), 3)
        self.assertEqual(agent.surrendered, 1)
        action = agent.policy({"container_list": containers, "pool_list": [dict(scene.items[0])]})
        self.assertEqual(agent.surrendered, 1)
        self.assertEqual(int(action["item_idx"]), 0)

    def test_alias_accepts_extra_overrides(self):
        arm = make_arm("ladder-stable@inclusion_clearance=0.008")
        self.assertTrue(arm.config.compaction_keeps_support)
        self.assertEqual(arm.config.key_quantum, 0.005)
        self.assertAlmostEqual(arm.config.inclusion_clearance, 0.008)
        self.assertEqual(arm.describe()["arm"], "ladder-stable@inclusion_clearance=0.008")


class MetricTests(unittest.TestCase):
    def _item(self, index, x, y, z, size=(0.5, 0.4, 0.2), soft=False, prio=False, cont_prio=False):
        hx, hy, hz = (s / 2 for s in size)
        return {
            "index": index, "is_soft": soft, "is_prioritized": prio,
            "container_is_prioritized": cont_prio,
            "aabb_min": [x - hx, y - hy, z - hz], "aabb_max": [x + hx, y + hy, z + hz],
        }

    def test_cover_from_above_counts_once_per_covered_item(self):
        base = self._item(0, 0, 0, 0.1, soft=True)
        on_top = self._item(1, 0.1, 0.0, 0.3)
        also = self._item(2, -0.1, 0.0, 0.3)
        out = attribute_violations([base, on_top, also], has_priority_container=False)
        self.assertEqual(out["soft_covered"], 1)
        self.assertEqual(out["priority_covered"], 0)

    def test_same_attribute_on_top_is_free(self):
        base = self._item(0, 0, 0, 0.1, prio=True)
        on_top = self._item(1, 0, 0, 0.3, prio=True)
        out = attribute_violations([base, on_top], has_priority_container=False)
        self.assertEqual(out["priority_covered"], 0)

    def test_misrouting_needs_a_priority_container(self):
        item = self._item(0, 0, 0, 0.1, prio=True, cont_prio=False)
        self.assertEqual(attribute_violations([item], False)["priority_misrouted"], 0)
        self.assertEqual(attribute_violations([item], True)["priority_misrouted"], 1)

    def test_gap_beyond_tolerance_is_not_a_cover(self):
        base = self._item(0, 0, 0, 0.1, soft=True)
        floating = self._item(1, 0, 0, 0.5)
        self.assertEqual(attribute_violations([base, floating], False)["soft_covered"], 0)


class CompareTests(unittest.TestCase):
    def _record(self, scene, placed, fill, steps):
        metrics = {m: 0.0 for m in COMPARED}
        metrics.update({"placed_count": placed, "fill_volume": fill, "end_reason": "declined"})
        return {"scene": scene, "arm": {"arm": "ladder"}, "metrics": metrics,
                "steps": [{"event": "step", "item_index": i, "pool_index": 0,
                           "container_idx": 0, "orientation": 0, "place_pos": [0, 0, 0],
                           "is_included": True, "is_valid": True, "is_placed_safe": True}
                          for i in range(steps)]}

    def test_identical_runs_pass_the_negative_control(self):
        a = {f"s{i}": self._record(f"s{i}", 10, 20.0, 10) for i in range(5)}
        result = compare.compare_runs(a, a, "x", "x")
        self.assertTrue(result["same_arm"])
        self.assertTrue(result["identical_steps"])
        self.assertEqual(result["metrics"]["placed_count"]["evidence"], "none")
        self.assertIn("PASS", compare.markdown(result))

    def test_consistent_gain_is_evidence(self):
        a = {f"s{i}": self._record(f"s{i}", 10, 20.0, 10) for i in range(12)}
        b = {f"s{i}": self._record(f"s{i}", 12 + (i % 2), 22.0, 12) for i in range(12)}
        result = compare.compare_runs(a, b, "a", "b")
        self.assertFalse(result["identical_steps"])
        row = result["metrics"]["placed_count"]
        self.assertEqual(row["evidence"], "b-better")
        self.assertEqual(row["better"], 12)
        self.assertGreater(row["ci95"][0], 0)

    def test_noise_is_not_evidence(self):
        rng = np.random.default_rng(1)
        a = {f"s{i}": self._record(f"s{i}", 10, 20.0, 10) for i in range(12)}
        b = {f"s{i}": self._record(f"s{i}", 10 + int(rng.integers(-2, 3)), 20.0, 10) for i in range(12)}
        result = compare.compare_runs(a, b, "a", "b")
        self.assertEqual(result["metrics"]["placed_count"]["evidence"], "none")

    def test_load_run_skips_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / "s1.json").write_text(json.dumps(self._record("s1", 1, 1.0, 1)))
            (path / "summary.json").write_text(json.dumps({"rows": []}))
            self.assertEqual(list(compare.load_run(path)), ["s1"])


class AnalyticRunnerTests(unittest.TestCase):
    def test_tiny_scene_runs_and_has_the_physics_schema(self):
        from bench.analytic import run_analytic_episode

        scene = make_scene(5, "c1", "C", items_per_container=6)
        record = run_analytic_episode(scene, make_arm("ladder"))
        metrics = record["metrics"]
        self.assertEqual(metrics["total_items"], 6)
        self.assertIn(metrics["end_reason"], ("stream-exhausted", "declined"))
        self.assertEqual(metrics["placed_count"], metrics["attempted"])
        for key in ("placed_count", "fill_volume", "com_z_above_floor_ratio",
                    "priority_covered", "soft_covered", "policy_time_max"):
            self.assertIn(key, metrics)
        self.assertNotIn("fill_evaluator_shipped", metrics)
        for step in record["steps"]:
            if step["event"] == "step":
                self.assertTrue(step["is_placed_safe"])
        # deterministic: the same scene gives the same placements
        again = run_analytic_episode(scene, make_arm("ladder"))
        self.assertEqual([s.get("place_pos") for s in record["steps"]],
                         [s.get("place_pos") for s in again["steps"]])


class AgreementTests(unittest.TestCase):
    def test_confusion_cells(self):
        records = [{"probes": [{"probes": [
            {"analytic_ok": True, "accepted": True, "analytic_reason": "survivor", "kind": "chosen"},
            {"analytic_ok": True, "accepted": False, "analytic_reason": "survivor", "kind": "survivor"},
            {"analytic_ok": False, "accepted": True, "analytic_reason": "no-support", "kind": "perturbed"},
            {"analytic_ok": False, "accepted": False, "analytic_reason": "no-support", "kind": "perturbed"},
        ]}]}]
        out = confusion(records)
        self.assertEqual(out["cells"], {"aa": 1, "ar": 1, "ra": 1, "rr": 1})
        self.assertAlmostEqual(out["false_accept_rate"], 0.5)
        self.assertAlmostEqual(out["false_reject_rate"], 0.5)
        self.assertEqual(out["by_analytic_reason"]["no-support"]["physics_accepted"], 1)


if __name__ == "__main__":
    unittest.main()
