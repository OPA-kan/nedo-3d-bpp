"""The restricted soft-first pass (``config.soft_first_restricted``):
where a soft item's pose may rest for the item to go before the hard
cargo -- on soft cargo, or on a hard top no hard or priority item of the
pool could stand on; never on a shelf, never on the floor."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.arms import make_arm  # noqa: E402
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1, surface  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import ContainerModel, make_container_dict  # noqa: E402

# the sample's Task B container (a chamfer, so a small shelf plate; no main shelf)
BOX = dict(length=2.0, width=1.52, height=1.62, thickness=0.02, cut_x=0.3, cut_y=0.3)
ULD = dict(length=2.0, width=1.45, height=1.61, thickness=0.04, cut_x=0.44, cut_y=0.40)
SPEC = "ladder-stable@soft_first_restricted=true,no_cover_other_attribute=true,fast_validate=true"


def _packed(index, x, y, dims, soft=False, prio=False, z0=0.02):
    return {"index": index, "length": dims[0], "width": dims[1], "height": dims[2], "mass": 8.0,
            "is_soft": soft, "is_prioritized": prio, "orientation": 0, "dims": dims,
            "pos": (x, y, z0 + dims[2] / 2.0)}


def _item(index, l, w, h, soft=False, prio=False):
    return {"index": index, "length": l, "width": w, "height": h, "mass": 5.0 if soft else 9.0,
            "is_soft": soft, "is_prioritized": prio}


def _agent(container, spec=SPEC):
    agent = make_arm(spec)(None)
    agent.get_init_states({"container_list": [container]})
    return agent


def _profile(agent, index, l, w, h, **flags):
    return cls.classify_item(index, _item(index, l, w, h, **flags), agent.config)


def _soft_box(x, y, bottom, dims=(0.45, 0.30, 0.20)):
    return AABB((x, y, bottom + dims[2] / 2.0), dims, "soft")


class ConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(DEFAULT_CONFIG.soft_first_restricted)
        self.assertEqual(DEFAULT_CONFIG.soft_first_restricted_share, 0.3)
        self.assertFalse(DEFAULT_CONFIG.soft_first_restricted_standing)


class VerdictTest(unittest.TestCase):
    """``_restricted_verdict`` on hand-built boards."""

    def _board(self, packed, spec=BOX, **kw):
        container = make_container_dict(index=0, **spec, **kw)
        container["packed_items"] = packed
        agent = _agent(container)
        return agent, container

    def test_floor_pose_is_refused(self):
        agent, _c = self._board([])
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.65, 0.45, 0.25)
        z_floor = agent.board.model(0).z_floor
        self.assertEqual(agent._restricted_verdict(_soft_box(0.4, -0.3, z_floor), 0, soft, [hard]), "floor")

    def test_shelf_pose_is_refused(self):
        agent, _c = self._board([], spec=ULD, require_shelf=True)
        model = agent.board.model(0)
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.65, 0.45, 0.25)
        for shelf in model.shelves:
            box = _soft_box(float(shelf.center[0]), float(shelf.center[1]), float(shelf.maximum[2]))
            self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "shelf", shelf.name)

    def test_a_hard_top_the_pools_hard_box_stands_on_is_refused(self):
        # the validator's rule is the centre of mass inside the contacts'
        # hull: a 0.65 x 0.45 box stands on a lone 0.55 x 0.40 top with
        # overhang, so the top is hard cargo's whatever the footprints say
        agent, _c = self._board([_packed(0, 0.4, 0.5, (0.55, 0.40, 0.24))])
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        box = _soft_box(0.4, 0.5, 0.02 + 0.24)
        for dims in ((0.65, 0.45, 0.25), (0.55, 0.40, 0.24)):
            hard = _profile(agent, 0, *dims)
            self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "top-usable", dims)
        # the pool's priority cargo counts as hard cargo
        prio = _profile(agent, 0, 0.65, 0.45, 0.25, prio=True)
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [prio]), "top-usable")
        # a pool without hard or priority cargo leaves the top to the soft box
        self.assertEqual(agent._restricted_verdict(box, 0, soft, []), "top")

    def test_a_hard_top_too_high_for_the_pools_hard_boxes_goes_to_the_soft(self):
        # a column whose top leaves 0.23 m under the ceiling: the 0.25 m
        # hard box of the pool does not fit with the inclusion clearance,
        # the 0.20 m soft box does
        agent, _c = self._board([_packed(0, 0.3, 0.3, (1.0, 1.0, 1.35))])
        model = agent.board.model(0)
        top = model.z_floor + 1.35
        self.assertLess(model.z_ceiling - top, 0.25)
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.65, 0.45, 0.25)
        box = _soft_box(0.3, 0.3, top)
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "top")
        # the same column 0.15 m lower holds the hard box
        agent, _c = self._board([_packed(0, 0.3, 0.3, (1.0, 1.0, 1.20))])
        hard = _profile(agent, 0, 0.65, 0.45, 0.25)
        self.assertEqual(agent._restricted_verdict(_soft_box(0.3, 0.3, model.z_floor + 1.20), 0, soft, [hard]), "top-usable")

    def _well(self):
        # a 0.5 x 0.5 top in a well between four taller columns: the pool's
        # 0.55 x 0.40 box has no free footprint in it, a 0.45 x 0.30 one has
        gap = 0.25 + 0.013 + 0.25
        packed = [_packed(0, 0.3, 0.3, (0.50, 0.50, 0.50)),
                  _packed(1, 0.3 - gap, 0.3, (0.50, 1.6, 0.90)),
                  _packed(2, 0.3 + gap, 0.3, (0.50, 1.6, 0.90)),
                  _packed(3, 0.3, 0.3 - gap, (0.50, 0.50, 0.90)),
                  _packed(4, 0.3, 0.3 + gap, (0.50, 0.50, 0.90))]
        return self._board(packed)

    def test_a_hard_top_hemmed_in_too_narrow_for_the_pools_hard_boxes_goes_to_the_soft(self):
        agent, _c = self._well()
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.55, 0.40, 0.24)
        box = _soft_box(0.3, 0.3, 0.02 + 0.50)
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "top")
        # a 0.45 x 0.30 hard box in the pool would stand there
        small = _profile(agent, 0, 0.45, 0.30, 0.24)
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [small]), "top-usable")

    def test_on_soft_cargo(self):
        agent, _c = self._board([_packed(0, 0.4, 0.5, (0.65, 0.35, 0.23), soft=True)])
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.55, 0.40, 0.24)
        self.assertEqual(agent._restricted_verdict(_soft_box(0.4, 0.5, 0.02 + 0.23), 0, soft, [hard]), "soft")
        # partly on soft cargo, partly on a hard top the hard box stands on
        # (the soft box at y 0.325..0.675, the hard top at -0.088..0.312,
        # the soft pose across the seam)
        agent, _c = self._board([_packed(0, 0.4, 0.5, (0.65, 0.35, 0.23), soft=True),
                                 _packed(1, 0.4, 0.5 - 0.175 - 0.013 - 0.20, (0.55, 0.40, 0.23))])
        box = _soft_box(0.4, 0.5 - 0.175 - 0.0065, 0.02 + 0.23, dims=(0.45, 0.30, 0.20))
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "top-usable")

    def test_a_priority_top_under_a_normal_soft_box_is_refused(self):
        agent, _c = self._board([_packed(0, 0.3, 0.3, (1.0, 1.0, 1.35), prio=True)])
        model = agent.board.model(0)
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.65, 0.45, 0.25)
        box = _soft_box(0.3, 0.3, model.z_floor + 1.35)
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "priority-top")
        soft_prio = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True, prio=True)
        self.assertEqual(agent._restricted_verdict(box, 0, soft_prio, [hard]), "top")

    def test_standing_poses_of_the_pools_hard_boxes_when_asked(self):
        # the well again: flat, the 0.55 x 0.40 box has no footprint in it;
        # standing on its 0.40 x 0.24 side it has, when the pass asks for
        # the standing poses
        agent, _c = self._well()
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        hard = _profile(agent, 0, 0.55, 0.40, 0.24)
        box = _soft_box(0.3, 0.3, 0.02 + 0.50)
        self.assertEqual(agent._restricted_windows([hard], False), [(0.55, 0.40, 0.24)])
        self.assertEqual(agent._restricted_windows([hard], True),
                         [(0.40, 0.24, 0.55), (0.55, 0.24, 0.40), (0.55, 0.40, 0.24)])
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "top")
        agent.config = agent.config.__class__(**{**agent.config.to_dict(), "soft_first_restricted_standing": True})
        self.assertEqual(agent._restricted_verdict(box, 0, soft, [hard]), "top-usable")


class TopHoldsTest(unittest.TestCase):
    """``surface.top_holds`` on a grid: the hull rule in each axis."""

    def _load(self, packed):
        container = make_container_dict(index=0, **BOX)
        container["packed_items"] = packed
        model = ContainerModel(container, DEFAULT_CONFIG)
        scorer = surface.scorer_for(DEFAULT_CONFIG)
        load = scorer.load(layer1.Board([container], DEFAULT_CONFIG), 0)
        return model, load

    def test_overhang_is_allowed_up_to_the_margin(self):
        model, load = self._load([_packed(0, 0.4, 0.5, (0.55, 0.40, 0.24))])
        seed = load.mask(AABB((0.4, 0.5, 0.14), (0.55, 0.40, 0.24), "top"))
        z = model.z_floor + 0.24
        self.assertTrue(surface.top_holds(load, z, seed, [(0.65, 0.45, 0.25)], 0.026, 0.02, 0.03))
        self.assertTrue(surface.top_holds(load, z, seed, [(1.0, 0.45, 0.25)], 0.026, 0.02, 0.03))
        # not a box so tall the ceiling refuses it
        self.assertFalse(surface.top_holds(load, z, seed, [(0.65, 0.45, 1.40)], 0.026, 0.02, 0.03))
        # not on a soft top
        model, load = self._load([_packed(0, 0.4, 0.5, (0.55, 0.40, 0.24), soft=True)])
        self.assertFalse(surface.top_holds(load, z, seed, [(0.65, 0.45, 0.25)], 0.026, 0.02, 0.03))

    def test_the_window_must_touch_the_seed(self):
        # two tops far apart at one height: a box on the other top does
        # not make this one hard cargo's
        model, load = self._load([_packed(0, 0.4, 0.5, (0.55, 0.40, 0.24)), _packed(1, 0.4, -0.5, (0.55, 0.40, 0.24))])
        z = model.z_floor + 0.24
        seed = load.mask(AABB((0.4, 0.5, 0.14), (0.55, 0.40, 0.24), "top"))
        self.assertTrue(surface.top_holds(load, z, seed, [(0.55, 0.40, 0.24)], 0.026, 0.02, 0.03))
        self.assertFalse(surface.top_holds(load, z, np.zeros_like(seed), [(0.55, 0.40, 0.24)], 0.026, 0.02, 0.03))


class PassTest(unittest.TestCase):
    """``_soft_first_restricted`` through ``policy``."""

    def _slab_board(self, slab_height):
        # the whole floor under one hard slab, the small shelf plate under
        # a block of the same top: the only surface is the slab's top
        container = make_container_dict(index=0, **BOX)
        model = ContainerModel(container, DEFAULT_CONFIG)
        r = model.floor_rect
        shelf = model.shelves[0]
        top = model.z_floor + slab_height
        container["packed_items"] = [
            _packed(0, (r.x_max + r.x_min) / 2, (r.y_max + r.y_min) / 2,
                    (r.x_max - r.x_min - 0.02, r.y_max - r.y_min - 0.02, slab_height)),
            _packed(1, float(shelf.center[0]), float(shelf.center[1]),
                    (float(shelf.size[0]) - 0.02, float(shelf.size[1]) - 0.02, top - float(shelf.maximum[2])),
                    z0=float(shelf.maximum[2])),
        ]
        return container, top

    def test_fires_on_a_top_no_hard_box_of_the_pool_fits(self):
        container, top = self._slab_board(1.20)
        # the pool's hard box is 0.40 m tall: 0.40 m of headroom over the
        # slab is not enough with the clearance; the 0.20 m soft box fits
        pool = [_item(0, 0.50, 0.40, 0.40), _item(1, 0.45, 0.30, 0.20, soft=True)]
        agent = _agent(container)
        action = agent.policy({"container_list": [container], "pool_list": pool})
        self.assertIsNotNone(action)
        self.assertEqual(int(action["item_idx"]), 1)
        self.assertEqual(agent.phase_stats.get("sfr_fired"), 1)
        self.assertEqual(agent.phase_stats.get("sfr_fired_top"), 1)
        self.assertEqual(agent.phase_stats.get("sfr_verdict_top"), 1)
        self.assertTrue(agent.last_decision.placement.reason.startswith("soft-first (restricted, on top, ladder)"))
        self.assertAlmostEqual(float(agent.last_decision.placement.box.minimum[2]), top, delta=0.01)
        # off: the pass leaves no trace
        agent = _agent(container, SPEC.replace("soft_first_restricted=true,", ""))
        agent.policy({"container_list": [container], "pool_list": pool})
        self.assertFalse(any(k.startswith("sfr_") for k in agent.phase_stats))

    def test_the_hard_box_goes_first_when_its_box_fits_the_top(self):
        container, _top = self._slab_board(1.20)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        agent = _agent(container)
        action = agent.policy({"container_list": [container], "pool_list": pool})
        self.assertIsNotNone(action)
        self.assertEqual(int(action["item_idx"]), 0)
        self.assertEqual(agent.phase_stats.get("sfr_verdict_top_usable"), 1)
        self.assertIsNone(agent.phase_stats.get("sfr_fired"))

    def test_the_shelf_pose_is_refused_and_the_hard_box_goes_first(self):
        container = make_container_dict(index=0, require_shelf=True, **ULD)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        agent = _agent(container)
        action = agent.policy({"container_list": [container], "pool_list": pool})
        self.assertEqual(int(action["item_idx"]), 0)
        self.assertEqual(agent.phase_stats.get("sfr_verdict_shelf"), 1)
        self.assertIsNone(agent.phase_stats.get("sfr_fired"))

    def test_the_floor_pose_is_refused(self):
        # an empty container with no main shelf: the ladder's pose for the
        # soft box is on the floor or on the small shelf plate, refused either way
        container = make_container_dict(index=0, **BOX)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        agent = _agent(container)
        action = agent.policy({"container_list": [container], "pool_list": pool})
        self.assertEqual(int(action["item_idx"]), 0)
        self.assertEqual(agent.phase_stats.get("sfr_verdict_floor", 0) + agent.phase_stats.get("sfr_verdict_shelf", 0), 1)
        self.assertIsNone(agent.phase_stats.get("sfr_fired"))

    def test_smallest_soft_item_first_and_the_verdict_decides(self):
        # the ladder stubbed: every soft item gets a pose on the floor but
        # the second-smallest, which gets one on soft cargo
        container = make_container_dict(index=0, **BOX)
        container["packed_items"] = [_packed(0, 0.4, 0.5, (0.65, 0.35, 0.23), soft=True)]
        agent = _agent(container)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.60, 0.30, 0.25, soft=True),
                _item(2, 0.45, 0.30, 0.20, soft=True), _item(3, 0.50, 0.40, 0.40, soft=True)]
        from rule_alpha.planner import _Pose, _placement

        asked = []

        def fake(board, profile, config, selector=None, **kw):
            asked.append(profile.index)
            model = board.model(0)
            orientation = profile.orientations[0]
            dims = (orientation.dx, orientation.dy, orientation.dz)
            if profile.index == 1:
                box = AABB((0.4, 0.5, model.z_floor + 0.23 + dims[2] / 2.0), dims, "s")
            else:
                box = AABB((0.4, -0.4, model.z_floor + dims[2] / 2.0), dims, "s")
            placement = _placement(_Pose(box, orientation, model.z_floor), 1, profile, 0, model)
            return layer1.Decision(placement=placement, candidate_counts={}, veto_counts={}, considered=1, ladder=[])

        with mock.patch.object(layer1, "choose_for_item", fake):
            agent._shadow_observation = None
            agent.board = layer1.Board([container], agent.config)
            agent.plan_by_index = {}
            agent._longest_call = 0.0
            action = agent._soft_first_restricted(
                [(i, cls.classify_item(i, it, agent.config)) for i, it in enumerate(pool)], float("inf"))
        self.assertEqual(asked, [2, 1])
        self.assertEqual(int(action["item_idx"]), 1)
        self.assertEqual(agent.phase_stats.get("sfr_verdict_floor"), 1)
        self.assertEqual(agent.phase_stats.get("sfr_fired_soft"), 1)
        self.assertEqual(agent.phase_stats.get("sfr_decisions"), 2)
        self.assertIsNone(agent.phase_stats.get("sfr_decisions_ladder-tops"))

    def test_the_tops_ask_follows_a_refused_pick(self):
        # the ladder stubbed: its own pick for the soft item is the floor,
        # its pick over item surfaces (the tops ask) rests on soft cargo;
        # the stack option is never reached
        container = make_container_dict(index=0, **BOX)
        container["packed_items"] = [_packed(0, 0.4, 0.5, (0.65, 0.35, 0.23), soft=True)]
        agent = _agent(container, SPEC + ",soft_first_restricted_tops=true")
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        from rule_alpha.planner import _Pose, _placement

        asked = []

        def fake(board, profile, config, selector=None, surfaces=None, **kw):
            asked.append((profile.index, surfaces, bool(config.soft_tops_for_soft)))
            model = board.model(0)
            orientation = profile.orientations[0]
            dims = (orientation.dx, orientation.dy, orientation.dz)
            if surfaces == ("item",):
                box = AABB((0.4, 0.5, model.z_floor + 0.23 + dims[2] / 2.0), dims, "s")
            else:
                box = AABB((0.4, -0.4, model.z_floor + dims[2] / 2.0), dims, "s")
            placement = _placement(_Pose(box, orientation, model.z_floor), 1, profile, 0, model)
            return layer1.Decision(placement=placement, candidate_counts={}, veto_counts={}, considered=1, ladder=[])

        class Stack:
            def propose(self, board, profile, deadline=None):
                raise AssertionError("the stack option is asked only after the ladder's tops ask")

        agent.stack_option = Stack()
        with mock.patch.object(layer1, "choose_for_item", fake):
            agent._shadow_observation = None
            agent.board = layer1.Board([container], agent.config)
            agent.plan_by_index = {}
            agent._longest_call = 0.0
            action = agent._soft_first_restricted(
                [(i, cls.classify_item(i, it, agent.config)) for i, it in enumerate(pool)], float("inf"))
        self.assertEqual(asked, [(1, None, False), (1, ("item",), True)])
        self.assertEqual(int(action["item_idx"]), 1)
        self.assertEqual(agent.phase_stats.get("sfr_verdict_floor"), 1)
        self.assertEqual(agent.phase_stats.get("sfr_fired_soft"), 1)
        self.assertEqual(agent.phase_stats.get("sfr_fired_ladder-tops"), 1)
        self.assertTrue(agent.last_decision.placement.reason.startswith("soft-first (restricted, on soft, ladder-tops)"))

    def test_the_ladder_takes_a_surface_restriction(self):
        # an empty container with a main shelf: the ladder's pick for a
        # soft item is the shelf; over item surfaces only there is none
        container = make_container_dict(index=0, require_shelf=True, **ULD)
        agent = _agent(container)
        soft = _profile(agent, 1, 0.45, 0.30, 0.20, soft=True)
        own = layer1.choose_for_item(agent.board, soft, agent.config)
        self.assertEqual(own.placement.surface, "shelf")
        self.assertIsNone(layer1.choose_for_item(agent.board, soft, agent.config, surfaces=("item",)))
        self.assertEqual(layer1.choose_for_item(agent.board, soft, agent.config, surfaces=("floor",)).placement.surface, "floor")


if __name__ == "__main__":
    unittest.main()
