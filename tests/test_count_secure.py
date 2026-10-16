"""Task A count-secured planning (``config.plan_count_secure``)."""

from __future__ import annotations

import dataclasses
import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.arms import make_arm  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from rule_alpha import count_secure, layer1  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import AABB  # noqa: E402

# the shipped Task A planner's fields (reports/bench/arms/arm_ship_a.txt)
# without the stack option and the dry-run, so a plan takes seconds
PLANNER = ("ladder-stable@offline_planner=rows,plan_variants=first;after-hard,plan_layouts=1,"
           "no_cover_other_attribute=true,priority_cargo_first=true,priority_is_structure=true,"
           "reserve_headroom_for_soft=true,soft_headroom_volume_share=0.9,soft_headroom_slack=0.05,"
           "plan_min_support=0.0,plan_standing=true,conservative_transport=false,count_first=true,"
           "plan_score_weights=1;0.5;0.5;3,plan_normal_in_priority_container=true,plan_priority_deep_first=true,"
           "cover_veto_ignores_shelf=true,soft_headroom_per_container=true,count_mode=true,count_mode_strict=true,"
           "soft_is_structure=true,soft_structure_max_top=0.7,soft_structure_floor_share=0.35,"
           "offline_budget_seconds=120")


def _plan(scene, spec):
    agent = make_arm(spec)(scene)
    containers = scene.rule_alpha_containers()
    agent.get_init_states({"container_list": containers})
    order = agent.optimize([dict(i) for i in scene.items])
    return agent, containers, order


class CountSecureConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(DEFAULT_CONFIG.plan_count_secure)
        self.assertFalse(DEFAULT_CONFIG.plan_count_secure_choice)

    def test_overrides_are_read_as_the_fields_types(self):
        got = count_secure.parse_overrides(DEFAULT_CONFIG, "plan_standing_rows=true;plan_band=0.3|plan_layouts=2")
        self.assertEqual(got, {"plan_standing_rows": True, "plan_band": 0.3, "plan_layouts": 2})


class CountFrameTest(unittest.TestCase):
    def _item(self, index, l, w, h, soft=False, prio=False):
        return {"index": index, "length": l, "width": w, "height": h, "mass": 5.0,
                "is_soft": soft, "is_prioritized": prio}

    def test_priority_always_then_the_smallest_across_classes(self):
        items = [
            self._item(0, 0.75, 0.56, 0.27),                # 113 L hard
            self._item(1, 0.65, 0.45, 0.25, prio=True),     # 73 L priority
            self._item(2, 0.45, 0.30, 0.20, soft=True),     # 27 L soft
            self._item(3, 0.55, 0.40, 0.24),                # 53 L hard
            self._item(4, 0.60, 0.30, 0.25, soft=True),     # 45 L soft
            self._item(5, 0.50, 0.40, 0.40, soft=True),     # 80 L soft
        ]
        frame = count_secure.count_frame(items, 4)
        self.assertEqual(frame, [1, 2, 4, 3])
        # a frame smaller than the priority cargo is the priority cargo
        self.assertEqual(count_secure.count_frame(items, 0), [1])
        self.assertEqual(sorted(count_secure.count_frame(items, 10)), list(range(6)))


class DenseManifestTest(unittest.TestCase):
    """c1x60 seed 2: 60 items in one container, the manifest 0.8 of its
    volume; the ordinary plan holds 27 against a threshold of 31."""

    @classmethod
    def setUpClass(cls):
        cls.scene = make_scene(2, "c1x60", "A")
        cls.threshold = len(cls.scene.items) // 2 + 1
        cls.base, _c, cls.base_order = _plan(cls.scene, PLANNER)
        cls.secured, cls.containers, cls.order = _plan(cls.scene, PLANNER + ",plan_count_secure=true")

    def test_flag_off_keeps_the_ordinary_plan(self):
        self.assertIsNone(getattr(self.base, "count_secure_log", None))
        self.assertLess(len(self.base.plan), self.threshold)

    def test_count_secured_plan_holds_more_items(self):
        log = self.secured.count_secure_log
        self.assertEqual(log["base"], len(self.base.plan))
        self.assertNotEqual(log["chosen"], "base")
        self.assertGreater(len(self.secured.plan), len(self.base.plan))
        self.assertGreaterEqual(len(self.secured.plan), self.threshold)
        self.assertEqual(sorted(self.order), sorted(int(i["index"]) for i in self.scene.items))
        self.assertEqual(self.order[:len(self.secured.plan)],
                         [e["index"] for e in sorted(self.secured.plan, key=lambda e: e["step"])])

    def test_count_secured_plan_is_legal_step_by_step(self):
        from rule_alpha.planner import _Pose, _placement

        board = layer1.Board(self.containers, self.secured.config)
        for entry in sorted(self.secured.plan, key=lambda e: e["step"]):
            model = board.model(entry["container_idx"])
            container = board.container(entry["container_idx"])
            box = AABB(tuple(entry["center"]), tuple(entry["size"]), "plan")
            ok, why = layer1.validate(box, model, container, self.secured.config)
            self.assertTrue(ok, why)
            profile = self.secured.profiles[entry["index"]]
            orientation = next(o for o in profile.orientations if o.index == entry["orientation"])
            board.apply(_placement(_Pose(box, orientation, model.z_floor), 1, profile, entry["container_idx"], model))

    def test_block_variant_keeps_the_soft_block_on_its_strip(self):
        agent = self.secured
        agent.plan_source = "planner"
        frame = count_secure.count_frame(self.scene.items, self.threshold + 2)
        items = [dict(i) for i in self.scene.items]
        import time

        _order, plan, info = count_secure.plan_frame(agent, items, time.perf_counter() + 60, frame, "left")
        agent.plan_source = ""
        self.assertEqual(len(info["regions"]), 1)
        x0, x1, _y0, _y1 = info["regions"][0]
        by_index = {int(i["index"]): i for i in items}
        in_frame = set(frame)
        soft_frame = [e for e in plan if by_index[e["index"]].get("is_soft") and e["index"] in in_frame
                      and e["step"] <= info["frame_planned"]]
        self.assertGreater(len(soft_frame), 0)
        for e in soft_frame[:4]:
            self.assertGreaterEqual(e["center"][0] - e["size"][0] / 2.0, x0 - 0.011)
            self.assertLessEqual(e["center"][0] + e["size"][0] / 2.0, x1 + 0.011)


class EarlyReplanTest(unittest.TestCase):
    def test_early_replan_with_one_base_variant_is_the_late_one(self):
        scene = make_scene(2, "c1x60", "A")
        late, _c, late_order = _plan(scene, PLANNER + ",plan_count_secure=true")
        early, _c2, early_order = _plan(scene, PLANNER + ",plan_count_secure=true,plan_count_secure_early=true")
        self.assertEqual(early.count_secure_log["chosen"], late.count_secure_log["chosen"])
        self.assertEqual(len(early.plan), len(late.plan))
        self.assertEqual(early_order, late_order)


class RaceTest(unittest.TestCase):
    """plan_count_secure_race_chosen: the count rule decides the planner /
    dry-run race only after a chosen re-plan, and never hands a plan that
    holds the threshold to the dry-run."""

    def setUp(self):
        scene = make_scene(2, "c1x60", "A")
        self.agent = make_arm(PLANNER)(scene)
        self.agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        self.agent._manifest_total = len(scene.items)   # threshold 31, gate 33
        self.agent.config = dataclasses.replace(self.agent.config, plan_count_secure=True,
                                                plan_count_secure_choice=True,
                                                plan_count_secure_race_chosen=True)

    def race(self, chosen, planner, dry):
        self.agent.count_secure_log = {"chosen": chosen, "replanned": True}
        return self.agent._count_secure_race([{}] * planner, [{}] * dry)

    def test_no_count_rule_without_a_chosen_replan(self):
        self.assertIsNone(self.race("base", 28, 34))
        self.assertIsNone(self.race("base", 34, 28))

    def test_a_plan_holding_the_threshold_is_not_handed_to_the_dry_run(self):
        self.assertIsNone(self.race("plain", 31, 34))
        self.assertIsNone(self.race("plain", 32, 40))

    def test_under_the_threshold_the_dry_run_over_the_gate_wins(self):
        self.assertEqual(self.race("plain", 30, 33), "dry-run")

    def test_the_replan_over_the_gate_wins_over_a_dry_run_under_it(self):
        self.assertEqual(self.race("plain", 33, 32), "planner")

    def test_v51_rule_kept_without_the_flag(self):
        self.agent.config = dataclasses.replace(self.agent.config, plan_count_secure_race_chosen=False,
                                                plan_count_secure_race_replanned=True)
        self.assertEqual(self.race("base", 31, 34), "dry-run")


class GateHeldTest(unittest.TestCase):
    def test_a_plan_over_the_gate_is_kept(self):
        # a sample-sized manifest whose ordinary plan holds the threshold
        # plus the margin: the flag changes nothing
        scene = make_scene(1, "c1", "A")
        base, _c, base_order = _plan(scene, PLANNER)
        secured, _c2, order = _plan(scene, PLANNER + ",plan_count_secure=true,plan_count_secure_choice=true")
        threshold = len(scene.items) // 2 + 1
        self.assertGreaterEqual(len(base.plan), threshold + 2)
        self.assertEqual(secured.count_secure_log["chosen"], "base")
        self.assertEqual(order, base_order)
        self.assertEqual([e["center"] for e in secured.plan], [e["center"] for e in base.plan])


if __name__ == "__main__":
    unittest.main()


class TailOrderTest(unittest.TestCase):
    """config.plan_tail_order: the order's tail after the chosen plan."""

    def _agent(self, mode):
        scene = make_scene(0, "sample", "A")
        agent = make_arm(f"ladder-stable@plan_tail_order={mode}")(scene)
        items = [dict(i) for i in scene.items]
        by_index = {int(i["index"]): i for i in items}
        # the shipped form's order on the sample: the 25 hard boxes planned,
        # the tail opening with two priority boxes
        order = [3, 17, 21, 33, 5, 9, 11, 19, 20, 22, 23, 35, 39, 0, 4, 6, 10, 12, 18, 24, 27, 29, 32, 36, 38,
                 8, 30, 14, 13, 16, 31, 34, 40, 1, 28, 15, 25, 26, 37, 2, 7]
        agent.plan = [{"index": i} for i in order[:25]]
        agent.plan_source = "dry-run"
        return agent, items, by_index, order

    def test_off_leaves_the_order(self):
        agent, items, _by, order = self._agent("")
        self.assertEqual(agent._tail_order(order, items), order)

    def test_soft_first_then_priority_then_hard(self):
        agent, items, by_index, order = self._agent("soft-first")
        got = agent._tail_order(order, items)
        self.assertEqual(got[:25], order[:25])
        self.assertEqual(sorted(got), sorted(order))
        tail = got[25:]
        kinds = ["S" if by_index[i]["is_soft"] else "P" if by_index[i]["is_prioritized"] else "H" for i in tail]
        self.assertEqual(kinds, ["S"] * 13 + ["P"] * 3)
        vols = [by_index[i]["length"] * by_index[i]["width"] * by_index[i]["height"] for i in tail[:13]]
        self.assertEqual(vols, sorted(vols))

    def test_priority_last_and_small_first(self):
        agent, items, by_index, order = self._agent("soft-first-prio-last")
        tail = agent._tail_order(order, items)[25:]
        self.assertTrue(all(by_index[i]["is_prioritized"] for i in tail[-3:]))
        agent, items, by_index, order = self._agent("small-first")
        tail = agent._tail_order(order, items)[25:]
        vols = [by_index[i]["length"] * by_index[i]["width"] * by_index[i]["height"] for i in tail]
        self.assertEqual(vols, sorted(vols))

    def test_planned_items_keep_their_order_whatever_their_place(self):
        agent, items, by_index, order = self._agent("soft-first")
        agent.plan = [{"index": i} for i in (14, 3, 8)]
        got = agent._tail_order(order, items)
        # 8 is the plan's trailing priority box and joins the tail; 14 and
        # 3 stay, in the order's own sequence
        self.assertEqual(got[:3], [3, 14, 2])
        kinds = ["S" if by_index[i]["is_soft"] else "P" if by_index[i]["is_prioritized"] else "H" for i in got[2:]]
        self.assertEqual(kinds, ["S"] * 12 + ["P"] * 3 + ["H"] * 24)
        self.assertEqual(sorted(got), sorted(order))

    def test_the_plans_trailing_special_items_join_the_tail(self):
        agent, items, by_index, order = self._agent("soft-first")
        # the sample's dry-run plan: the 25 hard boxes, then 8 (P), 30 (P), 14 (S)
        agent.plan = [{"index": i} for i in order[:28]]
        got = agent._tail_order(order, items)
        self.assertEqual(got[:25], order[:25])
        tail = got[25:]
        kinds = ["S" if by_index[i]["is_soft"] else "P" if by_index[i]["is_prioritized"] else "H" for i in tail]
        self.assertEqual(kinds, ["S"] * 13 + ["P"] * 3)
        self.assertEqual(sorted(got), sorted(order))
        # a soft box planned among the hard ones stays where the plan put it
        agent.plan = [{"index": i} for i in [3, 14, 17, 21, 8]]
        got = agent._tail_order(order, items)
        self.assertEqual(got[:4], [3, 17, 21, 14])
        self.assertEqual(got[4], 2)  # the smallest soft box of the tail
