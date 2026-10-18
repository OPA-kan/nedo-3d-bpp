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


class PlanScoreComTest(unittest.TestCase):
    """The fifth plan-score weight prices the plan's centre of mass."""

    def test_lower_load_scores_higher_with_the_fifth_weight(self):
        scene = make_scene(0, "sample", "A")
        items = [dict(i) for i in scene.items]
        for weights, expect_low_wins in (("0;0;0;0;1", True), ("0;0;0;0", False)):
            agent = make_arm(f"ladder-stable@plan_score_weights={weights},offline_dry_run=false,offline_planner=")(scene)
            agent.get_init_states({"container_list": scene.rule_alpha_containers()})
            agent.optimize(items)
            low = [{"index": 0, "container_idx": 0, "center": [0.0, 0.0, 0.2]}, {"index": 1, "container_idx": 0, "center": [0.5, 0.0, 0.2]}]
            high = [{"index": 0, "container_idx": 0, "center": [0.0, 0.0, 1.2]}, {"index": 1, "container_idx": 0, "place_pos": [0.5, 0.0, 1.2]}]
            if expect_low_wins:
                self.assertGreater(agent.plan_score(low), agent.plan_score(high))
            else:
                self.assertEqual(agent.plan_score(low), agent.plan_score(high))
class SoftFrameBlockTest(unittest.TestCase):
    """``plan_count_secure_blocks`` token ``soft`` (reports/wedge/a-soft-frame.md):
    the count frame's soft cargo standing two deep against the back wall
    (``count_secure.pack_soft_block``, ``planner.pack_typed_gallery`` mode
    ``column``), the frame's hard rows in front of it."""

    @classmethod
    def setUpClass(cls):
        cls.scene = make_scene(2, "c1x60", "A")
        cls.agent = make_arm(PLANNER)(cls.scene)
        cls.containers = cls.scene.rule_alpha_containers()
        cls.agent.get_init_states({"container_list": cls.containers})
        cls.items = [dict(i) for i in cls.scene.items]
        cls.agent._prepare_manifest(cls.items)
        cls.agent._manifest_total = len(cls.items)
        cls.agent.plan_source = "planner"
        cls.frame = count_secure.count_frame(cls.items, 33)

    def _block(self, **fields):
        import time

        config = dataclasses.replace(self.agent.config, **fields)
        board = layer1.Board([dict(c, packed_items=[]) for c in self.containers], config)
        soft = [self.agent.profiles[i] for i in self.frame if self.agent.profiles[i].is_soft]
        soft = [p for p in soft if not p.is_prioritized] + [p for p in soft if p.is_prioritized]
        plan, planned = [], []
        edge = count_secure.pack_soft_block(self.agent, board, 0, soft, config, plan, planned,
                                            time.perf_counter() + 60)
        return board, plan, edge

    def test_defaults_leave_the_block_out(self):
        self.assertEqual(DEFAULT_CONFIG.plan_count_secure_blocks, "plain")
        self.assertEqual(DEFAULT_CONFIG.plan_count_secure_soft_layers, 2)
        self.assertFalse(DEFAULT_CONFIG.plan_count_secure_soft_ledge)
        self.assertGreater(DEFAULT_CONFIG.plan_count_secure_soft_nudge, DEFAULT_CONFIG.plan_replay_nudge)

    def test_block_stands_two_deep_against_the_back_wall(self):
        board, plan, edge = self._block()
        model = board.model(0)
        by_index = {int(i["index"]): i for i in self.items}
        self.assertGreaterEqual(len(plan), 12)
        floor = [e for e in plan if e["on_floor"]]
        upper = [e for e in plan if not e["on_floor"]]
        self.assertGreaterEqual(len(upper), 3)
        back = model.floor_rect.y_max - self.agent.config.anchor_slack
        for e in plan:
            self.assertTrue(by_index[e["index"]]["is_soft"])
            # standing: the smallest face down, every entry with the block's replay nudge
            self.assertAlmostEqual(e["size"][2], max(e["size"]), places=6)
            self.assertAlmostEqual(e["replay_nudge"], DEFAULT_CONFIG.plan_count_secure_soft_nudge, places=6)
            self.assertLessEqual(e["center"][1] + e["size"][1] / 2.0, back + 1e-6)
        # the first row against the back wall, the floor share met before anything is stacked
        self.assertTrue(any(abs(e["center"][1] + e["size"][1] / 2.0 - back) < 1e-6 for e in floor))
        for e in upper:
            # on a floor box's top, under the soft structure cap, the same footprint or a smaller one
            base = next(f for f in floor if abs(f["bottom"] + f["size"][2] - e["bottom"]) < 1e-6
                        and abs(f["center"][0] - e["center"][0]) < 0.03 and abs(f["center"][1] - e["center"][1]) < 0.03)
            self.assertLessEqual(e["bottom"], model.z_floor + 0.7 + 1e-6)
            self.assertLessEqual(e["size"][0], base["size"][0] + 0.02 + 1e-6)
            self.assertLessEqual(e["size"][1], base["size"][1] + 0.02 + 1e-6)
            # nothing normal rests on a priority box
            if by_index[base["index"]]["is_prioritized"]:
                self.assertTrue(by_index[e["index"]]["is_prioritized"])
        # the rows keep the extra gap, so a row that settles towards the opening still clears the next
        lines = sorted({round(e["center"][1] + e["size"][1] / 2.0, 3) for e in floor}, reverse=True)
        gap = self.agent.config.settled_clearance + self.agent.config.anchor_slack
        for upper_line, lower_line in zip(lines, lines[1:]):
            front = min(e["center"][1] - e["size"][1] / 2.0 for e in floor
                        if abs(e["center"][1] + e["size"][1] / 2.0 - upper_line) < 1e-3)
            self.assertGreaterEqual(front - lower_line, gap + DEFAULT_CONFIG.plan_count_secure_soft_gap - 1e-3)
        self.assertAlmostEqual(edge, min(e["center"][1] - e["size"][1] / 2.0 for e in floor), places=6)

    def test_one_layer_keeps_every_box_on_the_floor(self):
        _board, plan, _edge = self._block(plan_count_secure_soft_layers=1)
        self.assertGreater(len(plan), 0)
        self.assertTrue(all(e["on_floor"] for e in plan))

    def test_ledge_stands_boxes_on_the_small_shelf(self):
        board, plan, _edge = self._block(plan_count_secure_soft_ledge=True)
        shelf = board.model(0).small_shelf
        self.assertIsNotNone(shelf)
        on_ledge = [e for e in plan if abs(e["bottom"] - float(shelf.maximum[2])) < 1e-6]
        self.assertGreaterEqual(len(on_ledge), 2)
        for e in on_ledge:
            self.assertLessEqual(e["center"][0] + e["size"][0] / 2.0, float(shelf.maximum[0]) + 1e-6)
            self.assertFalse(e["on_floor"])
        _board, plain, _e = self._block()
        self.assertFalse(any(abs(e["bottom"] - float(shelf.maximum[2])) < 1e-6 for e in plain))

    def test_frame_plan_puts_the_hard_rows_in_front_of_the_block(self):
        import time

        from rule_alpha.planner import _Pose, _placement

        agent = self.agent
        saved = agent.config
        # the count-secured overrides secure_count plans every variant with
        agent.config = dataclasses.replace(saved, plan_standing_rows=True, plan_soft_own_rows=True)
        try:
            _order, plan, info = count_secure.plan_frame(agent, self.items, time.perf_counter() + 90, self.frame,
                                                         "soft")
        finally:
            agent.config = saved
        self.assertEqual(len(info["regions"]), 1)
        _x0, _x1, edge, _y1 = info["regions"][0]
        by_index = {int(i["index"]): i for i in self.items}
        gap = agent.config.settled_clearance + agent.config.anchor_slack
        in_frame = set(self.frame)
        steps = sorted(plan, key=lambda e: e["step"])
        # the frame's hard rows start the block's gap in front of its edge
        # (the pose search over what the rows left anchors anywhere)
        hard = [e for e in steps[:info["frame_planned"]] if not by_index[e["index"]]["is_soft"]]
        self.assertGreater(len(hard), 0)
        for e in hard:
            self.assertLessEqual(e["center"][1] + e["size"][1] / 2.0,
                                 edge - gap - DEFAULT_CONFIG.plan_count_secure_soft_gap + 1e-3)
        self.assertTrue(all(e["index"] in in_frame for e in steps[:info["frame_planned"]]))
        self.assertGreater(sum(1 for e in steps if by_index[e["index"]]["is_soft"] and e["index"] in in_frame), 10)
        board = layer1.Board([dict(c, packed_items=[]) for c in self.containers], agent.config)
        for entry in steps:
            model = board.model(entry["container_idx"])
            box = AABB(tuple(entry["center"]), tuple(entry["size"]), "plan")
            ok, why = layer1.validate(box, model, board.container(entry["container_idx"]), agent.config)
            self.assertTrue(ok, why)
            profile = agent.profiles[entry["index"]]
            orientation = next(o for o in profile.orientations if o.index == entry["orientation"])
            board.apply(_placement(_Pose(box, orientation, model.z_floor), 1, profile, entry["container_idx"], model))

    def test_replay_slides_a_block_pose_by_its_own_nudge(self):
        from rule_alpha.planner import _replay

        agent = self.agent
        config = dataclasses.replace(agent.config, plan_replay_clearance=0.026, plan_replay_nudge=0.02)
        saved = agent.config
        agent.config = config
        try:
            soft = [p for p in agent.profiles.values() if p.is_soft and not p.is_prioritized
                    and abs(p.orientations[0].dx - 0.65) < 1e-9]
            first, second = soft[0], soft[1]
            o = next(oo for oo in first.orientations if abs(oo.dz - 0.65) < 1e-9 and abs(oo.dx - 0.23) < 1e-9)
            board = layer1.Board([dict(c, packed_items=[]) for c in self.containers], config)
            model = board.model(0)
            rect = model.floor_rect
            x = rect.x_min + 0.2
            y_back = rect.y_max - config.anchor_slack - o.dy / 2.0
            z = model.z_floor + o.dz / 2.0
            # the first box settled against the back wall; the second planned
            # touching its front (a row that settled 2.6 cm towards it)
            board.container(0)["packed_items"].append(dict(
                index=first.index, position=[x, y_back, z], dims=[o.dx, o.dy, o.dz], is_soft=True,
                is_prioritized=False))
            entry = {"step": 2, "index": second.index, "container_idx": 0, "orientation": int(o.index),
                     "center": [x, y_back - o.dy, z], "size": [o.dx, o.dy, o.dz], "bottom": model.z_floor,
                     "on_floor": True}
            pool = [(0, second)]
            agent.plan_misses = 0
            self.assertIsNone(_replay(agent, board, pool, {second.index: dict(entry)}))
            hit = _replay(agent, board, pool, {second.index: dict(entry, replay_nudge=0.04)})
            self.assertIsNotNone(hit)
            placed = hit[1].placement.box
            self.assertLess(float(placed.center[1]), y_back - o.dy - 0.02)
            self.assertGreaterEqual(y_back - o.dy / 2.0 - float(placed.maximum[1]), 0.026 - 1e-6)
        finally:
            agent.config = saved


class DensePlanTest(unittest.TestCase):
    """``plan_count_secure_blocks`` token ``dense`` (reports/wedge/a-dense.md):
    the flat hard layers, the frame's soft boxes standing on the chamfer
    ledge, the standing layer with the priority hard boxes last, then the
    soft layers over the top under the re-plan's own soft-structure cap
    (``plan_count_secure_soft_cap``), which the replay validates under."""

    @classmethod
    def setUpClass(cls):
        import time

        cls.scene = make_scene(3, "c1x80", "A")
        cls.agent = make_arm(PLANNER + ",plan_standing_rows=true,plan_soft_own_rows=true,"
                             "plan_standing_rows_max_height=0.4,plan_count_secure_soft_cap=1.6")(cls.scene)
        cls.containers = cls.scene.rule_alpha_containers()
        cls.agent.get_init_states({"container_list": cls.containers})
        cls.items = [dict(i) for i in cls.scene.items]
        cls.agent._prepare_manifest(cls.items)
        cls.agent._manifest_total = len(cls.items)
        cls.agent.plan_source = "planner"
        cls.threshold = len(cls.items) // 2 + 1
        cls.frame = count_secure.count_frame(cls.items, cls.threshold + 2)
        cls.by_index = {int(i["index"]): i for i in cls.items}
        cap = count_secure._plan_soft_cap(cls.agent.config)
        with cap:
            cls.order, cls.plan, cls.info = count_secure.plan_dense(cls.agent, cls.items, time.perf_counter() + 120,
                                                                   cls.frame)
        cls.capped = cap.mark(cls.plan, cls.by_index)

    def test_defaults_leave_the_dense_plan_out(self):
        self.assertEqual(DEFAULT_CONFIG.plan_count_secure_blocks, "plain")
        self.assertLess(DEFAULT_CONFIG.plan_count_secure_soft_cap, 0.0)
        self.assertTrue(DEFAULT_CONFIG.plan_count_secure_dense_ledge)

    def test_layers_in_carrying_order(self):
        steps = sorted(self.plan, key=lambda e: e["step"])
        model = self.agent.board.model(0)
        shelf_top = float(model.small_shelf.maximum[2])
        n_flat, n_ledge, n_stand = self.info["flat"], self.info["ledge"], self.info["standing"]
        flat = steps[:n_flat]
        ledge = steps[n_flat:n_flat + n_ledge]
        standing = steps[n_flat + n_ledge:n_flat + n_ledge + n_stand]
        self.assertGreaterEqual(n_flat, 10)
        self.assertGreaterEqual(n_ledge, 4)
        self.assertGreaterEqual(n_stand, 10)
        # the flat layers: hard, flat, two deep at most
        for e in flat:
            self.assertFalse(self.by_index[e["index"]]["is_soft"])
            self.assertAlmostEqual(e["size"][2], min(e["size"]), places=6)
        self.assertLess(max(e["bottom"] + e["size"][2] for e in flat), 0.6)
        # the ledge: the frame's normal soft boxes standing on the small
        # shelf's top, inside its width, before the standing layer
        for e in ledge:
            item = self.by_index[e["index"]]
            self.assertTrue(item["is_soft"] and not item["is_prioritized"] and e["index"] in set(self.frame))
            self.assertAlmostEqual(e["bottom"], shelf_top, places=3)
            self.assertAlmostEqual(e["size"][2], max(e["size"]), places=6)
            self.assertLessEqual(e["center"][0] + e["size"][0] / 2.0, float(model.small_shelf.maximum[0]) + 1e-6)
        # the standing layer on edge (0.40 m tall), the priority boxes last
        for e in standing:
            self.assertFalse(self.by_index[e["index"]]["is_soft"])
            self.assertLessEqual(e["size"][2], 0.4 + 1e-6)
        prio = [k for k, e in enumerate(standing) if self.by_index[e["index"]]["is_prioritized"]]
        if prio:
            self.assertEqual(prio, list(range(len(standing) - len(prio), len(standing))))

    def test_soft_layers_two_deep_under_the_plan_cap(self):
        soft = [e for e in self.plan if self.by_index[e["index"]]["is_soft"] and not e["on_floor"]]
        # a second soft layer over the first, above the online cap of 0.7 m
        self.assertTrue(any(e["bottom"] > 1.1 for e in soft if e["bottom"] > 0.9))
        self.assertEqual(self.capped, len(soft))
        for e in soft:
            self.assertAlmostEqual(e["soft_cap"], 1.6, places=6)
        self.assertGreaterEqual(len(self.plan), self.threshold)
        self.assertEqual(self.order[:len(self.plan)], [e["index"] for e in sorted(self.plan, key=lambda e: e["step"])])

    def test_plan_is_legal_step_by_step_under_the_cap(self):
        from rule_alpha.planner import _Pose, _placement

        config = self.agent.config
        board = layer1.Board([dict(c, packed_items=[]) for c in self.containers], config)
        with count_secure._plan_soft_cap(config):
            for entry in sorted(self.plan, key=lambda e: e["step"]):
                model = board.model(entry["container_idx"])
                box = AABB(tuple(entry["center"]), tuple(entry["size"]), "plan")
                ok, why = layer1.validate(box, model, board.container(entry["container_idx"]), config)
                self.assertTrue(ok, f"step {entry['step']}: {why}")
                profile = self.agent.profiles[entry["index"]]
                orientation = next(o for o in profile.orientations if o.index == entry["orientation"])
                board.apply(_placement(_Pose(box, orientation, model.z_floor), 1, profile, entry["container_idx"],
                                       model))

    def test_replay_lifts_the_cap_for_a_capped_pose_only(self):
        from rule_alpha import stability
        from rule_alpha.planner import replay

        agent = self.agent
        soft = [p for p in agent.profiles.values() if p.is_soft and not p.is_prioritized
                and abs(p.orientations[0].dx - 0.65) < 1e-9]
        first, second = soft[0], soft[1]
        o = next(oo for oo in first.orientations if abs(oo.dz - 0.23) < 1e-9 and abs(oo.dx - 0.65) < 1e-9)
        board = layer1.Board([dict(c, packed_items=[]) for c in self.containers], agent.config)
        model = board.model(0)
        rect = model.floor_rect
        x, y = rect.x_min + 0.5, rect.y_max - 0.4
        # a hard column to 0.94 m, a flat soft box on it (top 1.17 m), and
        # the plan's pose for a second soft box on that one
        hard = [p for p in agent.profiles.values() if not p.is_soft and abs(p.orientations[0].dx - 0.65) < 1e-9]
        z = model.z_floor
        for h in hard[:2]:
            oh = next(oo for oo in h.orientations if abs(oo.dz - 0.45) < 1e-9 and abs(oo.dx - 0.65) < 1e-9)
            board.container(0)["packed_items"].append(dict(index=h.index, position=[x, y, z + oh.dz / 2.0],
                                                           dims=[oh.dx, oh.dy, oh.dz], is_soft=False,
                                                           is_prioritized=False))
            z += oh.dz
        board.container(0)["packed_items"].append(dict(index=first.index, position=[x, y, z + o.dz / 2.0],
                                                       dims=[o.dx, o.dy, o.dz], is_soft=True, is_prioritized=False))
        z += o.dz
        self.assertGreater(z, 0.7)
        entry = {"step": 9, "index": second.index, "container_idx": 0, "orientation": int(o.index),
                 "center": [x, y, z + o.dz / 2.0], "size": [o.dx, o.dy, o.dz], "bottom": z, "on_floor": False}
        pool = [(0, second)]
        agent.plan_misses = 0
        saved = (stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE)
        try:
            stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE = 0.7, 0.35
            self.assertIsNone(replay(agent, board, pool, {second.index: dict(entry)}))
            hit = replay(agent, board, pool, {second.index: dict(entry, soft_cap=1.6)})
            self.assertIsNotNone(hit)
            self.assertAlmostEqual(float(hit[1].placement.box.minimum[2]), z, places=3)
            # the online cap is back once the replay returns
            self.assertEqual((stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE), (0.7, 0.35))
        finally:
            stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE = saved


class DensePriorityStripTest(unittest.TestCase):
    """The dense plan's priority levers (reports/wedge/a-dense-quality.md):
    ``plan_count_secure_dense_priority_rows`` reserves the standing layer's
    front strip for the priority hard boxes and keeps the normal soft rows
    behind it, ``plan_count_secure_dense_soft_thin`` lays the flat soft
    boxes before the tall ones, ``plan_count_secure_dense_priority_fill``
    puts the priority hard boxes first in the fill passes."""

    FLAGS = (",plan_count_secure_dense_priority_rows=1,plan_count_secure_dense_soft_thin=0.25,"
             "plan_count_secure_dense_priority_fill=true")

    @classmethod
    def setUpClass(cls):
        import time

        cls.scene = make_scene(3, "c1x80", "A")
        cls.agent = make_arm(PLANNER + ",plan_standing_rows=true,plan_soft_own_rows=true,"
                             "plan_standing_rows_max_height=0.4,plan_count_secure_soft_cap=1.6" + cls.FLAGS)(cls.scene)
        cls.containers = cls.scene.rule_alpha_containers()
        cls.agent.get_init_states({"container_list": cls.containers})
        cls.items = [dict(i) for i in cls.scene.items]
        cls.agent._prepare_manifest(cls.items)
        cls.agent._manifest_total = len(cls.items)
        cls.agent.plan_source = "planner"
        cls.threshold = len(cls.items) // 2 + 1
        cls.frame = count_secure.count_frame(cls.items, cls.threshold + 2)
        cls.by_index = {int(i["index"]): i for i in cls.items}
        with count_secure._plan_soft_cap(cls.agent.config):
            cls.order, cls.plan, cls.info = count_secure.plan_dense(cls.agent, cls.items, time.perf_counter() + 120,
                                                                   cls.frame)

    def _kind(self, entry):
        item = self.by_index[entry["index"]]
        return bool(item["is_soft"]), bool(item["is_prioritized"])

    def test_defaults_leave_the_levers_out(self):
        self.assertEqual(DEFAULT_CONFIG.plan_count_secure_dense_priority_rows, 0)
        self.assertEqual(DEFAULT_CONFIG.plan_count_secure_dense_soft_thin, 0.0)
        self.assertFalse(DEFAULT_CONFIG.plan_count_secure_dense_priority_fill)

    def test_strip_is_the_shallowest_standing_pose_a_row(self):
        config = self.agent.config
        model = self.agent.board.model(0)
        prio = [p for p in self.agent.profiles.values() if p.is_prioritized and not p.is_soft
                and abs(p.orientations[0].dx - 0.55) < 1e-9]
        self.assertEqual(len(prio), 4)
        gap = config.settled_clearance + config.anchor_slack
        # on edge the 0.55 x 0.40 x 0.24 box is 0.24 m deep and 0.55 m wide: two a row
        depth, rows = count_secure.priority_strip(model, config, prio, 1)
        self.assertEqual(rows, 1)
        self.assertAlmostEqual(depth, 0.24 + gap, places=6)
        depth, rows = count_secure.priority_strip(model, config, prio, 3)
        self.assertEqual(rows, 2)
        self.assertAlmostEqual(depth, 2 * (0.24 + gap), places=6)
        self.assertEqual(count_secure.priority_strip(model, config, prio[:2], 3)[1], 1)
        # the 0.75 x 0.56 x 0.27 boxes have no standing pose under the 0.40 m cap
        tall = [p for p in self.agent.profiles.values() if p.is_prioritized and abs(p.orientations[0].dx - 0.75) < 1e-9]
        self.assertIsNone(count_secure.priority_strip(model, config, tall, 2))
        self.assertIsNone(count_secure.priority_strip(model, config, prio, 0))

    def test_priority_boxes_stand_in_the_front_strip_with_nothing_normal_over_them(self):
        steps = sorted(self.plan, key=lambda e: e["step"])
        n_flat, n_ledge, n_stand = self.info["flat"], self.info["ledge"], self.info["standing"]
        standing = steps[n_flat + n_ledge:n_flat + n_ledge + n_stand]
        prio = [e for e in standing if self._kind(e) == (False, True)]
        normal = [e for e in standing if self._kind(e) == (False, False)]
        self.assertEqual(self.info["priority_strip"]["rows"], 1)
        self.assertEqual(len(prio), 2)
        self.assertGreaterEqual(len(normal), 8)
        # the strip is in front of every normal standing box, loaded after them
        front = min(e["center"][1] - e["size"][1] / 2.0 for e in normal)
        for e in prio:
            self.assertLessEqual(e["center"][1] + e["size"][1] / 2.0, front + 1e-6)
            self.assertLessEqual(e["size"][2], 0.4 + 1e-6)
        self.assertLess(max(e["step"] for e in normal), min(e["step"] for e in prio))
        # no normal box of any class sits over a priority box in the plan
        for p in [e for e in self.plan if self._kind(e)[1]]:
            for e in self.plan:
                if self._kind(e)[1] or e["bottom"] < p["bottom"] + p["size"][2] - 1e-6:
                    continue
                dx = min(e["center"][0] + e["size"][0] / 2.0, p["center"][0] + p["size"][0] / 2.0) \
                    - max(e["center"][0] - e["size"][0] / 2.0, p["center"][0] - p["size"][0] / 2.0)
                dy = min(e["center"][1] + e["size"][1] / 2.0, p["center"][1] + p["size"][1] / 2.0) \
                    - max(e["center"][1] - e["size"][1] / 2.0, p["center"][1] - p["size"][1] / 2.0)
                self.assertFalse(dx > 1e-6 and dy > 1e-6, f"step {e['step']} over priority step {p['step']}")

    def test_flat_soft_boxes_before_the_tall_ones(self):
        steps = sorted(self.plan, key=lambda e: e["step"])
        soft = [e for e in steps if self._kind(e) == (True, False) and e["bottom"] > 0.9]
        tall = [k for k, e in enumerate(soft) if min(e["size"]) > 0.25 + 1e-6]
        thin = [k for k, e in enumerate(soft) if min(e["size"]) <= 0.25 + 1e-6]
        self.assertTrue(thin)
        if tall:
            self.assertLess(max(thin), min(tall))

    def test_fill_takes_the_priority_boxes_first_and_the_count_holds(self):
        # the strip's two, and the fill's standing slot at the layer's
        # right edge goes to a priority box (the shipped plan's normal one)
        n_prio = sum(1 for e in self.plan if self._kind(e) == (False, True))
        self.assertGreaterEqual(n_prio, 3)
        self.assertGreaterEqual(len(self.plan), self.threshold)

    def test_plan_is_legal_step_by_step_under_the_cap(self):
        from rule_alpha.planner import _Pose, _placement

        config = self.agent.config
        board = layer1.Board([dict(c, packed_items=[]) for c in self.containers], config)
        with count_secure._plan_soft_cap(config):
            for entry in sorted(self.plan, key=lambda e: e["step"]):
                model = board.model(entry["container_idx"])
                box = AABB(tuple(entry["center"]), tuple(entry["size"]), "plan")
                ok, why = layer1.validate(box, model, board.container(entry["container_idx"]), config)
                self.assertTrue(ok, f"step {entry['step']}: {why}")
                profile = self.agent.profiles[entry["index"]]
                orientation = next(o for o in profile.orientations if o.index == entry["orientation"])
                board.apply(_placement(_Pose(box, orientation, model.z_floor), 1, profile, entry["container_idx"],
                                       model))


class AdaptiveDenseTest(unittest.TestCase):
    """``plan_count_secure_dense_adaptive`` (reports/wedge/a-mix.md): the
    dense tokens' standing cap and thin-soft threshold read off the
    manifest; the shipped values on the sample mix, other values on
    another mix."""

    ARM = pathlib.Path(REPO_ROOT, "reports", "bench", "arms", "arm_adenser_a.txt").read_text().strip() \
        + ",offline_budget_seconds=30"
    TOKENS = ["plain", "dense", "dense@plan_standing_rows_max_height=0.4",
              "dense@plan_standing_rows_max_height=0.4&plan_count_secure_dense_priority_rows=1"
              "&plan_count_secure_dense_soft_thin=0.25"]

    @staticmethod
    def _synthetic(hard: tuple, n_hard: int = 40, n_soft: int = 40):
        """``n_hard`` boxes of one hard class and ``n_soft`` soft boxes of
        the sample's four soft classes, a priority item in ten."""
        import random

        from bench.scenes import SKUS

        rng = random.Random(7)
        soft_skus = [s for s in SKUS if s[5]]
        items = []
        for k in range(n_hard + n_soft):
            if k < n_hard:
                l, w, h, mass, soft, physics = hard[0], hard[1], hard[2], 12, False, dict(SKUS[0][6])
            else:
                _n, l, w, h, mass, soft, physics, _w = soft_skus[k % len(soft_skus)]
            items.append({"index": k, "length": l, "width": w, "height": h, "mass": mass, "is_soft": soft,
                          "is_prioritized": rng.random() < 0.1, **physics})
        rng.shuffle(items)
        for k, item in enumerate(items):
            item["index"] = k
        return items

    def _dense_plan(self, scene, items, extra: str):
        import time

        agent = make_arm(PLANNER + ",plan_standing_rows=true,plan_soft_own_rows=true,plan_count_secure_soft_cap=1.6"
                         + extra)(scene)
        containers = scene.rule_alpha_containers()
        agent.get_init_states({"container_list": containers})
        agent._prepare_manifest(items)
        agent._manifest_total = len(items)
        agent.plan_source = "planner"
        frame = count_secure.count_frame(items, len(items) // 2 + 1 + 2)
        with count_secure._plan_soft_cap(agent.config):
            _order, plan, info = count_secure.plan_dense(agent, items, time.perf_counter() + 120, frame)
        return agent, plan, info

    def test_defaults_off(self):
        self.assertFalse(DEFAULT_CONFIG.plan_count_secure_dense_adaptive)
        self.assertEqual(DEFAULT_CONFIG.plan_count_secure_dense_soft_layers, 0)
        self.assertFalse(DEFAULT_CONFIG.plan_row_depths_from_manifest)

    def test_sample_mix_derives_the_shipped_numbers(self):
        scene = make_scene(0, "sample", "A")
        items = [dict(i) for i in scene.items]
        agent = make_arm(self.ARM)(scene)
        agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        tokens, derived = count_secure.adaptive_dense_tokens(agent, items, self.TOKENS)
        self.assertEqual(tokens, ["plain", "dense", "dense@plan_count_secure_dense_soft_layers=2",
                                  "dense@plan_count_secure_dense_soft_layers=2&plan_count_secure_dense_priority_rows=1"
                                  "&plan_count_secure_dense_soft_thin=0.25"])
        self.assertEqual(derived["soft_layers"], 2)
        self.assertAlmostEqual(derived["soft_thin"], 0.25)
        # the thin threshold: the first class 1.4 times the next; none -> one pass
        from rule_alpha import classify as cls
        soft = [cls.classify_item(int(i["index"]), i, agent.config) for i in items if i["is_soft"]]
        self.assertAlmostEqual(count_secure.soft_thin_threshold(soft), 0.25)
        flat = [p for p in soft if min(o.dz for o in p.orientations) < 0.3]
        self.assertEqual(count_secure.soft_thin_threshold(flat), 0.0)
        self.assertEqual(count_secure.soft_layers_needed(agent.board, soft), 2)
        self.assertEqual(count_secure.soft_layers_needed(agent.board, soft[:4]), 1)
        # the cap in the plan: the on-edge 0.40 of the 0.55 x 0.40 x 0.24
        # class over the flat layers' 0.54 m top (11 standing, two soft
        # layers of 8) over 0.55 on end (15 standing, one layer: the
        # second would top 1.55 m, over the carry-in ceiling of 1.5255)
        # and over no standing layer (a soft layer on the flat top ends
        # in the mid-height band)
        model = agent.board.model(0)
        container = agent.board.container(0)
        self.assertAlmostEqual(count_secure.carry_in_ceiling(model, agent.config), 1.5255, places=4)
        self.assertTrue(count_secure.carry_in_ok(0.94, 1.17, model, container, agent.config))
        self.assertTrue(count_secure.carry_in_ok(1.17, 1.40, model, container, agent.config))
        self.assertFalse(count_secure.carry_in_ok(1.32, 1.55, model, container, agent.config))
        self.assertFalse(count_secure.carry_in_ok(0.54, 0.77, model, container, agent.config))
        self.assertFalse(count_secure.carry_in_ok(0.86, 1.09, model, container, agent.config))
        hard = [cls.classify_item(int(i["index"]), i, agent.config) for i in items
                if not i["is_soft"] and abs(i["length"] - 0.55) < 1e-9]
        with count_secure._plan_soft_cap(agent.config):   # the re-plan's 1.6 m soft cap
            cap, info = count_secure.dense_standing_cap(model, container, agent.config, hard, soft, 0.54, 2)
            self.assertAlmostEqual(cap, 0.40)
            self.assertEqual((info["layers"], info["standing"], info["soft"]), (2, 10, 13))
            by_cap = {c["cap"]: c for c in info["candidates"]}
            self.assertEqual((by_cap[0.55]["standing"], by_cap[0.55]["layers"]), (13, 1))
            self.assertEqual(by_cap[0.0]["soft"], 0)
            cap, info = count_secure.dense_standing_cap(model, container, agent.config, hard, soft, 0.54, 1)
            self.assertAlmostEqual(cap, 0.55)
            self.assertEqual(info["layers"], 1)
        # under the online cap (0.7 m) soft carries no second layer up there
        cap, info = count_secure.dense_standing_cap(model, container, agent.config, hard, soft, 0.54, 2)
        self.assertAlmostEqual(cap, 0.55)
        # the plan itself: the sample's dense plan with the layers field is
        # the plan with the fixed cap
        _a, fixed, _i = self._dense_plan(scene, items, ",plan_standing_rows_max_height=0.4")
        _b, adaptive, info = self._dense_plan(scene, items, ",plan_count_secure_dense_soft_layers=2")
        self.assertAlmostEqual(info["standing_cap"]["cap"], 0.40)
        self.assertEqual([(e["index"], e["center"], e["size"]) for e in fixed],
                         [(e["index"], e["center"], e["size"]) for e in adaptive])

    def test_official_sample_plan_is_unchanged_under_the_flag(self):
        scene = make_scene(0, "sample", "A")
        base, _c, base_order = _plan(scene, self.ARM)
        adaptive, _c2, order = _plan(scene, self.ARM + ",plan_count_secure_dense_adaptive=true,"
                                     "plan_row_depths_from_manifest=true")
        log = adaptive.count_secure_log
        self.assertTrue(log["replanned"])
        self.assertEqual(log["adaptive"]["tokens"][:2], ["plain", "dense"])
        self.assertTrue(log["chosen"].startswith("dense"))
        self.assertEqual(base.count_secure_log["chosen"].split("@")[0], log["chosen"].split("@")[0])
        self.assertEqual(order, base_order)
        self.assertEqual([(e["index"], e["center"], e["size"]) for e in adaptive.plan],
                         [(e["index"], e["center"], e["size"]) for e in base.plan])
        self.assertEqual(adaptive._manifest_row_depths, ([0.56, 0.45, 0.4, 0.27, 0.25, 0.24], [0.56, 0.45, 0.4]))
        self.assertIsNone(base._manifest_row_depths)

    def test_another_hard_class_gets_its_own_cap_and_a_fuller_plan(self):
        scene = make_scene(0, "sample", "A")
        items = self._synthetic((0.60, 0.50, 0.25))
        _a, fixed, info_fixed = self._dense_plan(scene, items, ",plan_standing_rows_max_height=0.4")
        _b, adaptive, info = self._dense_plan(scene, items, ",plan_count_secure_dense_soft_layers=2")
        # no standing pose of the 0.60 x 0.50 x 0.25 class is under 0.40,
        # so the fixed cap stands nothing and the soft rows on the 0.54 m
        # flat top end in the mid-height band; the 0.50 m pose stands ten
        # with one soft layer over them under the soft headroom reserve
        self.assertEqual(info_fixed["standing"], 0)
        self.assertAlmostEqual(info["standing_cap"]["cap"], 0.50)
        self.assertEqual(info["standing_cap"]["layers"], 1)
        self.assertGreater(info["standing"], 0)
        self.assertGreater(len(adaptive), len(fixed))
        agent = make_arm(self.ARM)(scene)
        agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        tokens, _d = count_secure.adaptive_dense_tokens(agent, items, self.TOKENS)
        self.assertEqual(len(tokens), 4)
        self.assertIn("plan_count_secure_dense_soft_layers=", tokens[2])
        self.assertNotIn("plan_standing_rows_max_height", ";".join(tokens))


class ManifestRowDepthsTest(unittest.TestCase):
    def test_table_and_default_from_the_hard_classes(self):
        from rule_alpha.planner import ROW_DEPTH_CLASSES, manifest_row_depths, online_row_lines

        scene = make_scene(0, "sample", "A")
        table, flat = manifest_row_depths(scene.items)
        self.assertEqual(table, [0.56, 0.45, 0.4, 0.27, 0.25, 0.24])
        self.assertEqual(flat, [0.56, 0.45, 0.4])
        self.assertIsNone(manifest_row_depths([i for i in scene.items if i["is_soft"]]))
        self.assertEqual(manifest_row_depths([{"length": 0.7, "width": 0.5, "height": 0.3, "is_soft": False}]),
                         ([0.5, 0.3], [0.5]))
        self.assertEqual(ROW_DEPTH_CLASSES, [0.56, 0.45, 0.40, 0.35, 0.30])
        agent = make_arm("ladder-stable")(scene)
        agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        model = agent.board.model(0)
        default = online_row_lines(model, agent.config, [])
        self.assertEqual(default, online_row_lines(model, agent.config, [], classes=None))
        other = online_row_lines(model, agent.config, [], classes=[0.5, 0.3])
        self.assertTrue(other)
        self.assertTrue(all(d in (0.5, 0.3) for _y, d in other))
        self.assertAlmostEqual(other[0][1], 0.5)
