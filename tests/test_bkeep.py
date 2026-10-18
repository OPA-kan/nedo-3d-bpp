"""Task B's keep-count variants of the content levers
(reports/wedge/b-keep-count.md): the deferral for the soft cargo only
(``config.pool_defer_soft_only``) and the deferral's floor hold under the
count threshold (``config.pool_defer_floor_secured``)."""

from __future__ import annotations

import pathlib
import sys
import unittest
from types import SimpleNamespace

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.arms import make_arm  # noqa: E402
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import make_container_dict  # noqa: E402

# the sample's Task B container (a chamfer, so a small shelf plate; no main shelf)
BOX = dict(length=2.0, width=1.52, height=1.62, thickness=0.02, cut_x=0.3, cut_y=0.3)
# a chamfer too small for a shelf plate any box fits on (a zero cut is a degenerate polygon)
PLAIN = dict(length=2.0, width=1.52, height=1.62, thickness=0.02, cut_x=0.05, cut_y=0.05)
SPEC = "ladder-stable@no_cover_other_attribute=true,fast_validate=true"


def _item(index, l, w, h, soft=False, prio=False):
    return {"index": index, "length": l, "width": w, "height": h, "mass": 5.0 if soft else 9.0,
            "is_soft": soft, "is_prioritized": prio}


def _agent(container, spec=SPEC):
    agent = make_arm(spec)(None)
    agent.get_init_states({"container_list": [container]})
    return agent


class ConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(DEFAULT_CONFIG.pool_defer_soft_only)
        self.assertFalse(DEFAULT_CONFIG.pool_defer_floor_secured)


class SoftOnlyOrderTest(unittest.TestCase):
    """``_defer_order`` with the priority cargo kept in the pool order."""

    def _agent_and_pairs(self, spec_tail):
        container = make_container_dict(index=0, **BOX)
        agent = _agent(container, SPEC + spec_tail)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.55, 0.40, 0.24), _item(2, 0.45, 0.30, 0.20, soft=True),
                _item(3, 0.60, 0.30, 0.25, soft=True), _item(4, 0.40, 0.30, 0.25, prio=True)]
        profiles = [(i, cls.classify_item(it["index"], it, agent.config)) for i, it in enumerate(pool)]
        return agent, layer1.pool_order(profiles, agent.config)

    def test_a_priority_item_at_k_keeps_its_place(self):
        agent, ordered = self._agent_and_pairs(",pool_defer_max=3,pool_defer_soft_only=true")
        agent._passed_over = {4: 9}
        self.assertEqual(agent._defer_order(ordered), ordered)
        self.assertFalse(agent._deferred_now)

    def test_a_soft_item_at_k_still_goes_first(self):
        agent, ordered = self._agent_and_pairs(",pool_defer_max=3,pool_defer_soft_only=true")
        agent._passed_over = {2: 3, 4: 9}
        out = agent._defer_order(ordered)
        self.assertEqual(out[0][1].index, 2)
        self.assertEqual(agent._deferred_now, {2})
        # the priority box stays where the pool order put it, after the hard cargo
        self.assertEqual([pr.index for _pi, pr in out[1:]], [pr.index for _pi, pr in ordered if pr.index != 2])

    def test_off_the_priority_item_is_deferred(self):
        agent, ordered = self._agent_and_pairs(",pool_defer_max=3")
        agent._passed_over = {4: 3}
        self.assertEqual(agent._defer_order(ordered)[0][1].index, 4)


class FloorHoldTest(unittest.TestCase):
    """The floor hold through ``policy`` on an empty container without a
    shelf plate (a plain box: on the chamfered one the soft box's ladder
    pose is on the shelf, which is not held): the soft box passed over k
    times has a floor pose, and under the count threshold it is held and
    the hard box goes first."""

    def _observation(self):
        container = make_container_dict(index=0, **PLAIN)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        return container, {"container_list": [container], "pool_list": pool}

    def test_under_the_threshold_the_floor_pose_is_held(self):
        container, observation = self._observation()
        agent = _agent(container, SPEC + ",pool_defer_max=3,pool_defer_floor_secured=true,count_mode=true")
        agent._passed_over = {1: 3}
        action = agent.policy(observation)
        self.assertIsNotNone(action)
        self.assertEqual(int(action["item_idx"]), 0)
        self.assertEqual(agent.phase_stats.get("defer_calls"), 1)
        self.assertEqual(agent.phase_stats.get("defer_floor_held"), 1)
        self.assertIsNone(agent.phase_stats.get("defer_fired"))
        self.assertIsNone(agent.phase_stats.get("defer_passed"))
        # the held item's count restarted, then it was passed over once by this placement
        self.assertEqual(agent._passed_over, {1: 1})

    def test_without_the_count_mode_nothing_is_held(self):
        container, observation = self._observation()
        agent = _agent(container, SPEC + ",pool_defer_max=3,pool_defer_floor_secured=true")
        agent._passed_over = {1: 3}
        action = agent.policy(observation)
        self.assertEqual(int(action["item_idx"]), 1)
        self.assertEqual(agent.phase_stats.get("defer_fired"), 1)
        self.assertIsNone(agent.phase_stats.get("defer_floor_held"))

    def test_off_the_floor_pose_fires(self):
        container, observation = self._observation()
        agent = _agent(container, SPEC + ",pool_defer_max=3,count_mode=true")
        agent._passed_over = {1: 3}
        action = agent.policy(observation)
        self.assertEqual(int(action["item_idx"]), 1)
        self.assertEqual(agent.phase_stats.get("defer_fired"), 1)


class FloorHoldRuleTest(unittest.TestCase):
    """``_defer_floor_hold`` on its own: the surface, the threshold, the
    deferred front."""

    def _agent(self):
        container = make_container_dict(index=0, **BOX)
        agent = _agent(container, SPEC + ",pool_defer_max=3,pool_defer_floor_secured=true,count_mode=true")
        agent.policy({"container_list": [container], "pool_list": [_item(0, 0.65, 0.45, 0.25)]})
        agent._deferred_now = {1}
        agent._passed_over = {1: 3}
        return agent

    def test_a_shelf_pose_is_not_held(self):
        agent = self._agent()
        agent._placed_now = 0
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        self.assertFalse(agent._defer_floor_hold(pool, 1, SimpleNamespace(surface="shelf")))
        self.assertEqual(agent._passed_over, {1: 3})

    def test_a_floor_pose_once_secured_is_not_held(self):
        agent = self._agent()
        agent._placed_now = int(agent._count_threshold())
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        self.assertFalse(agent._defer_floor_hold(pool, 1, SimpleNamespace(surface="floor")))

    def test_a_floor_pose_under_the_threshold_is_held(self):
        agent = self._agent()
        agent._placed_now = int(agent._count_threshold()) - 1
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        self.assertTrue(agent._defer_floor_hold(pool, 1, SimpleNamespace(surface="floor")))
        self.assertEqual(agent._passed_over, {1: 0})
        self.assertFalse(agent._deferred_now)

    def test_an_item_not_at_the_front_is_not_held(self):
        agent = self._agent()
        agent._placed_now = 0
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        self.assertFalse(agent._defer_floor_hold(pool, 0, SimpleNamespace(surface="floor")))


if __name__ == "__main__":
    unittest.main()
