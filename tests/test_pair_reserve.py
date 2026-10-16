"""The same-class pair reservation on Task B (config.pair_reserve,
rule_alpha/pair.py): a pool holding two 0.55 x 0.40 x 0.24 boxes on an
empty floor; the first pose leaves room beside it for the second, and the
second lands flush beside the first on the next call."""

from __future__ import annotations

import dataclasses
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rule_alpha import pair  # noqa: E402
from rule_alpha.agent import RuleAlphaAgent  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import make_container_dict  # noqa: E402

ULD = dict(length=2.0, width=1.45, height=1.61, thickness=0.04, cut_x=0.44, cut_y=0.40)
ON = dataclasses.replace(DEFAULT_CONFIG, pair_reserve=True, deterministic_budgets=True)
OFF = dataclasses.replace(DEFAULT_CONFIG, pair_reserve=False, deterministic_budgets=True)


def _item(index, dims=(0.55, 0.40, 0.24), soft=False, prio=False, mass=8.0):
    return {"index": index, "length": dims[0], "width": dims[1], "height": dims[2],
            "mass": mass, "is_soft": soft, "is_prioritized": prio}


def _packed(container, placement):
    """The observation's packed-item dict for a placement, as the board writes it."""
    item = placement.profile.item
    centre = placement.box.center
    offset_x = float(container.get("center", (0.0, 0.0, 0.0))[0])
    return {
        "index": placement.profile.index, "length": float(item["length"]), "width": float(item["width"]),
        "height": float(item["height"]), "mass": placement.profile.mass,
        "is_prioritized": placement.profile.is_prioritized, "is_soft": placement.profile.is_soft,
        "orientation": placement.orientation.index, "dims": tuple(float(v) for v in placement.box.size),
        "pos": (float(centre[0]) + offset_x, float(centre[1]), float(centre[2])),
    }


class PairGeometryTest(unittest.TestCase):
    def test_the_narrow_top_and_the_pair_that_holds_the_window(self):
        # the 0.55 x 0.40 top is 3 cm short of the window either way round
        self.assertTrue(pair.narrow_top(0.55, 0.40, ON))
        self.assertTrue(pair.narrow_top(0.40, 0.55, ON))
        # the 0.65 x 0.45 top holds the window alone
        self.assertFalse(pair.narrow_top(0.65, 0.45, ON))
        gap = ON.settled_clearance + ON.pair_reserve_slack
        # two 0.55 x 0.40 tops side by side along the short axis (y): 0.55 x 0.836
        self.assertTrue(pair.pair_holds_window(0.55, 0.40, gap, 1, ON))
        # along the long axis: 1.136 x 0.40, no window
        self.assertFalse(pair.pair_holds_window(0.55, 0.40, gap, 0, ON))
        self.assertTrue(pair.pair_holds_window(0.40, 0.55, gap, 0, ON))
        self.assertFalse(pair.pair_holds_window(0.40, 0.55, gap, 1, ON))
        first = AABB((0.0, 0.0, 0.16), (0.55, 0.40, 0.24), "first")
        self.assertEqual({d[0] for d in pair.directions(first, gap, ON)}, {1})
        # the preferred direction first, otherwise the deeper spot first
        self.assertEqual(pair.directions(first, gap, ON)[0], (1, 1))
        self.assertEqual(pair.directions(first, gap, ON, preferred=(1, -1))[0], (1, -1))
        spot = pair.spot_box(first, 1, -1, gap, 0.04)
        self.assertAlmostEqual(float(first.minimum[1]) - float(spot.maximum[1]), gap, places=9)
        self.assertAlmostEqual(float(spot.minimum[2]), 0.04, places=9)

    def test_the_partner_is_the_same_class_and_dimensions(self):
        pool = [_item(0), _item(1, (0.65, 0.45, 0.25)), _item(2, (0.40, 0.24, 0.55)), _item(3, soft=True)]
        self.assertEqual(pair.same_class_partner(pool, 0, pool[0]), (2, 2))
        self.assertIsNone(pair.same_class_partner(pool[:2] + pool[3:], 0, pool[0]))
        self.assertTrue(pair.is_flat((0.55, 0.40, 0.24)))
        self.assertFalse(pair.is_flat((0.24, 0.40, 0.55)))


class PairReserveAgentTest(unittest.TestCase):
    def _agent(self, config):
        container = make_container_dict(index=0, **ULD)
        agent = RuleAlphaAgent(config=config)
        agent.get_init_states({"container_list": [container]})
        return agent, container

    def _gap_between(self, a: AABB, b: AABB):
        """(axis, gap) along the one axis the two boxes are apart on."""
        for axis in (0, 1):
            gap = max(float(b.minimum[axis]) - float(a.maximum[axis]),
                      float(a.minimum[axis]) - float(b.maximum[axis]))
            if gap > 0.0:
                return axis, gap
        return None, 0.0

    def test_the_first_pose_leaves_room_and_the_second_lands_flush(self):
        agent, container = self._agent(ON)
        # the pair, and a soft box the ladder's order puts behind them
        pool = [_item(0), _item(1), _item(2, (0.50, 0.40, 0.30), soft=True)]
        action = agent.policy({"container_list": [container], "pool_list": pool})
        self.assertIsNotNone(action)
        first = agent.last_decision.placement
        self.assertEqual(first.surface, "floor")
        self.assertIn(int(action["item_idx"]), (0, 1))
        self.assertEqual(agent.phase_stats.get("pair_eligible"), 1)
        self.assertEqual(agent.phase_stats.get("pair_reserved"), 1)
        reservation = agent._pair_reservation
        self.assertIsNotNone(reservation)
        first_index = int(pool[int(action["item_idx"])]["index"])
        partner_index = 1 - first_index
        self.assertEqual(reservation["first"], first_index)
        self.assertEqual(reservation["partner"], partner_index)
        # the next call: the first box settled where it was commanded, the
        # partner still in the pool, a new item behind it
        container["packed_items"] = [_packed(container, first)]
        pool2 = [p for p in pool if int(p["index"]) != first_index] + [_item(3, (0.75, 0.56, 0.27))]
        action2 = agent.policy({"container_list": [container], "pool_list": pool2})
        self.assertIsNotNone(action2)
        second = agent.last_decision.placement
        self.assertEqual(second.archetype, "pair-reserve")
        self.assertEqual(int(pool2[int(action2["item_idx"])]["index"]), partner_index)
        self.assertEqual(agent.phase_stats.get("pair_honoured"), 1)
        self.assertIsNone(agent._pair_reservation)
        # flush beside the first along the axis whose pair holds the window
        axis, gap = self._gap_between(first.box, second.box)
        self.assertEqual(axis, reservation["direction"][0])
        self.assertAlmostEqual(gap, ON.settled_clearance + ON.pair_reserve_slack, places=6)
        other = 1 - axis
        self.assertAlmostEqual(float(first.box.center[other]), float(second.box.center[other]), places=6)
        self.assertEqual(tuple(round(float(v), 4) for v in first.box.size),
                         tuple(round(float(v), 4) for v in second.box.size))
        self.assertAlmostEqual(float(second.box.minimum[2]), agent.board.model(0).z_floor, places=6)
        # the two tops together hold the window the one alone could not
        extent = max(float(first.box.maximum[axis]), float(second.box.maximum[axis])) - min(
            float(first.box.minimum[axis]), float(second.box.minimum[axis]))
        self.assertGreaterEqual(extent, 0.55 + pair.CLEAR)

    def test_the_reservation_is_lost_when_the_partner_has_gone(self):
        agent, container = self._agent(ON)
        pool = [_item(0), _item(1)]
        action = agent.policy({"container_list": [container], "pool_list": pool})
        first = agent.last_decision.placement
        self.assertEqual(agent.phase_stats.get("pair_reserved"), 1)
        container["packed_items"] = [_packed(container, first)]
        # the partner is no longer visible: the call falls through to the ladder
        action2 = agent.policy({"container_list": [container], "pool_list": [_item(5, (0.65, 0.45, 0.25))]})
        self.assertIsNotNone(action2)
        self.assertNotEqual(agent.last_decision.placement.archetype, "pair-reserve")
        self.assertEqual(agent.phase_stats.get("pair_lost"), 1)
        self.assertEqual(agent.phase_stats.get("pair_lost_partner"), 1)
        self.assertIsNone(agent.phase_stats.get("pair_honoured"))

    def test_the_reservation_is_lost_when_the_spot_is_taken(self):
        agent, container = self._agent(ON)
        pool = [_item(0), _item(1)]
        agent.policy({"container_list": [container], "pool_list": pool})
        first = agent.last_decision.placement
        reservation = dict(agent._pair_reservation)
        axis, sign = reservation["direction"]
        gap = ON.settled_clearance + ON.pair_reserve_slack
        # another box settled on the spot meanwhile
        spot = pair.spot_box(first.box, axis, sign, gap, agent.board.model(0).z_floor)
        intruder = dataclasses.replace(first, box=spot)
        intruder.profile = dataclasses.replace(first.profile, index=7, item=_item(7))
        container["packed_items"] = [_packed(container, first), _packed(container, intruder)]
        partner = [p for p in pool if int(p["index"]) != reservation["first"]]
        action2 = agent.policy({"container_list": [container], "pool_list": partner})
        self.assertIsNotNone(action2)
        self.assertNotEqual(agent.last_decision.placement.archetype, "pair-reserve")
        self.assertEqual(agent.phase_stats.get("pair_lost"), 1)

    def test_off_by_default_and_a_pool_of_one(self):
        agent, container = self._agent(OFF)
        agent.policy({"container_list": [container], "pool_list": [_item(0), _item(1)]})
        self.assertIsNone(agent._pair_reservation)
        self.assertNotIn("pair_eligible", agent.phase_stats)
        agent, container = self._agent(ON)
        agent.policy({"container_list": [container], "pool_list": [_item(0)]})
        self.assertIsNone(agent._pair_reservation)
        self.assertNotIn("pair_eligible", agent.phase_stats)

    def test_a_wide_top_or_a_lone_class_makes_no_reservation(self):
        agent, container = self._agent(ON)
        # two 0.65 x 0.45 boxes: the top holds the window alone
        agent.policy({"container_list": [container],
                      "pool_list": [_item(0, (0.65, 0.45, 0.25)), _item(1, (0.65, 0.45, 0.25))]})
        self.assertIsNone(agent._pair_reservation)
        self.assertNotIn("pair_eligible", agent.phase_stats)
        agent, container = self._agent(ON)
        # one narrow box and no partner of its class
        agent.policy({"container_list": [container], "pool_list": [_item(0), _item(1, (0.65, 0.45, 0.25))]})
        self.assertIsNone(agent._pair_reservation)
        self.assertNotIn("pair_eligible", agent.phase_stats)


if __name__ == "__main__":
    unittest.main()
