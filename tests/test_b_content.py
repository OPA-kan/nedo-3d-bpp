"""Task B's content levers (reports/wedge/b-content.md): the never-cover
rule for priority cargo (``config.priority_never_covered``: no pose of the
count pass or the grid rescue over a priority box, under the threshold
too) and the deferral limit (``config.pool_defer_max``: a soft or priority
pool item passed over k times goes to the front of the ladder's order)."""

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
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import make_container_dict  # noqa: E402
from wedge_rl.stack import stack_candidates  # noqa: E402

# the sample's Task B container (a chamfer, so a small shelf plate; no main shelf)
BOX = dict(length=2.0, width=1.52, height=1.62, thickness=0.02, cut_x=0.3, cut_y=0.3)
SPEC = "ladder-stable@no_cover_other_attribute=true,fast_validate=true"

PRIORITY_BASE = {"index": 1, "length": 0.75, "width": 0.56, "height": 0.27, "mass": 8.0,
                 "is_soft": False, "is_prioritized": True}
SOFT_BASE = dict(PRIORITY_BASE, is_soft=True, is_prioritized=False)
HARD_ITEM = {"index": 7, "length": 0.4, "width": 0.3, "height": 0.25, "mass": 5.0,
             "is_soft": False, "is_prioritized": False}


def _item(index, l, w, h, soft=False, prio=False):
    return {"index": index, "length": l, "width": w, "height": h, "mass": 5.0 if soft else 9.0,
            "is_soft": soft, "is_prioritized": prio}


def _agent(container, spec=SPEC):
    agent = make_arm(spec)(None)
    agent.get_init_states({"container_list": [container]})
    return agent


class ConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(DEFAULT_CONFIG.priority_never_covered)
        self.assertEqual(DEFAULT_CONFIG.pool_defer_max, 0)
        self.assertTrue(DEFAULT_CONFIG.count_cover_priority)


class NeverCoverGeneratorTest(unittest.TestCase):
    """The count pass's generator (``stack_candidates`` with the cover rule
    lifted) under the never-cover rule."""

    def _containers(self, base):
        containers = make_scene(1, "c1", "C").rule_alpha_containers()
        thickness = float(containers[0]["thickness"])
        packed = dict(base, pos=(0.3, 0.2, thickness + base["height"] / 2.0), orn=(0.0, 0.0, 0.0, 1.0))
        containers[0]["packed_items"].append(packed)
        return containers, thickness + base["height"]

    def _on_the_base(self, config, base, stats=None) -> int:
        containers, top = self._containers(base)
        board = layer1.Board(containers, config)
        profile = cls.classify_item(HARD_ITEM["index"], HARD_ITEM, config)
        cands = stack_candidates(board.model(0), board.container(0), config, profile,
                                 max_candidates=400, mass=5.0, tower_min=None, dense=0.04, stats=stats)
        self.assertTrue(cands, "the floor alone should give candidates")
        return sum(1 for c in cands if abs(c.bottom - top) < 0.01)

    def setUp(self):
        self.count_pass = dataclasses.replace(
            DEFAULT_CONFIG, no_cover_other_attribute=True, priority_is_structure=True,
            conservative_transport=False, routing_any_container=True, stack_max_bottom=10.0,
            allow_cover_other_attribute=True, soft_is_structure=True, stack_soft_is_structure=True,
        )

    def test_the_count_pass_covers_priority_cargo_by_default(self):
        # count_cover_priority on, as under the threshold proper
        self.assertGreater(self._on_the_base(self.count_pass, PRIORITY_BASE), 0)

    def test_a_priority_cover_is_refused_under_the_rule(self):
        stats = {}
        config = dataclasses.replace(self.count_pass, priority_never_covered=True)
        self.assertEqual(self._on_the_base(config, PRIORITY_BASE, stats), 0)
        self.assertGreater(stats.get("priority_cover_refused", 0), 0)

    def test_the_rule_leaves_the_soft_covers_to_the_count_pass(self):
        # soft cargo may still be covered: the never-cover rule is for the
        # priority box's credit alone
        config = dataclasses.replace(self.count_pass, priority_never_covered=True)
        self.assertGreater(self._on_the_base(config, SOFT_BASE), 0)


class PriorityCoverAllowedTest(unittest.TestCase):
    """``_priority_cover_allowed``: the one reading the count pass and the
    grid rescue share."""

    def _agent(self, **over):
        container = make_container_dict(index=0, **BOX)
        spec = SPEC + "".join(f",{k}={str(v).lower()}" for k, v in over.items())
        return _agent(container, spec)

    def test_under_the_threshold_the_count_pass_may_cover(self):
        agent = self._agent()
        agent._really_under = True
        self.assertTrue(agent._priority_cover_allowed(True))
        agent.config = dataclasses.replace(agent.config, count_cover_priority=False)
        self.assertTrue(agent._priority_cover_allowed(True), "count_cover_priority off narrows the low phase only")

    def test_over_the_threshold_the_switch_decides(self):
        agent = self._agent()
        agent._really_under = False
        self.assertTrue(agent._priority_cover_allowed(True))
        agent.config = dataclasses.replace(agent.config, count_cover_priority=False)
        self.assertFalse(agent._priority_cover_allowed(True))

    def test_never_means_never(self):
        agent = self._agent(priority_never_covered=True)
        for under in (True, False):
            agent._really_under = under
            self.assertFalse(agent._priority_cover_allowed(True))
            self.assertFalse(agent._priority_cover_allowed(False))

    def test_outside_the_count_pass_the_cover_rule_decides(self):
        agent = self._agent()
        self.assertTrue(agent._priority_cover_allowed(False))


class DeferOrderTest(unittest.TestCase):
    """``_defer_order`` on a hand-built pool."""

    def _agent_and_pairs(self, k=3):
        container = make_container_dict(index=0, **BOX)
        agent = _agent(container, SPEC + f",pool_defer_max={k}")
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.55, 0.40, 0.24), _item(2, 0.45, 0.30, 0.20, soft=True),
                _item(3, 0.60, 0.30, 0.25, soft=True), _item(4, 0.40, 0.30, 0.25, prio=True)]
        profiles = [(i, cls.classify_item(it["index"], it, agent.config)) for i, it in enumerate(pool)]
        return agent, layer1.pool_order(profiles, agent.config)

    def test_the_pool_order_puts_the_soft_and_priority_cargo_last(self):
        _agent_, ordered = self._agent_and_pairs()
        tail = [pr.index for _pi, pr in ordered][-3:]
        self.assertEqual(tail[0], 4)
        self.assertEqual(set(tail[1:]), {2, 3})

    def test_a_soft_item_passed_over_k_times_goes_first(self):
        agent, ordered = self._agent_and_pairs(k=3)
        agent._passed_over = {2: 3}
        out = agent._defer_order(ordered)
        self.assertEqual(out[0][1].index, 2)
        self.assertEqual([pr.index for _pi, pr in out[1:]], [pr.index for _pi, pr in ordered if pr.index != 2])
        self.assertEqual(agent._deferred_now, {2})
        self.assertEqual(agent.phase_stats.get("defer_calls"), 1)
        self.assertEqual(agent.phase_stats.get("defer_items"), 1)

    def test_under_k_the_order_holds(self):
        agent, ordered = self._agent_and_pairs(k=3)
        agent._passed_over = {2: 2, 4: 2}
        self.assertEqual(agent._defer_order(ordered), ordered)
        self.assertFalse(agent._deferred_now)
        self.assertNotIn("defer_calls", agent.phase_stats)

    def test_a_hard_item_is_never_deferred_to_the_front(self):
        agent, ordered = self._agent_and_pairs(k=3)
        agent._passed_over = {0: 9}
        self.assertEqual(agent._defer_order(ordered), ordered)

    def test_several_deferred_items_keep_the_pool_order(self):
        # priority before soft, the soft boxes in the pool order's own
        # sequence (not by how often each was passed over)
        agent, ordered = self._agent_and_pairs(k=3)
        agent._passed_over = {2: 4, 3: 6, 4: 3}
        out = agent._defer_order(ordered)
        typed = [pr.index for _pi, pr in ordered if pr.index in (2, 3, 4)]
        hard = [pr.index for _pi, pr in ordered if pr.index in (0, 1)]
        self.assertEqual([pr.index for _pi, pr in out], typed + hard)
        self.assertEqual(out[0][1].index, 4)
        self.assertEqual(agent.phase_stats.get("defer_items"), 3)
        # the same items on the next call are not new
        agent._defer_order(ordered)
        self.assertEqual(agent.phase_stats.get("defer_items"), 3)
        self.assertEqual(agent.phase_stats.get("defer_calls"), 2)

    def test_off_leaves_the_order(self):
        agent, ordered = self._agent_and_pairs(k=0)
        agent._passed_over = {2: 9}
        self.assertEqual(agent._defer_order(ordered), ordered)


class DeferPolicyTest(unittest.TestCase):
    """The deferral through ``policy`` on an empty container: the hard box
    goes first until the soft box has been passed over k times."""

    def _observation(self):
        container = make_container_dict(index=0, **BOX)
        pool = [_item(0, 0.65, 0.45, 0.25), _item(1, 0.45, 0.30, 0.20, soft=True)]
        return container, {"container_list": [container], "pool_list": pool}

    def test_the_hard_box_goes_first_and_the_soft_box_is_passed_over(self):
        container, observation = self._observation()
        agent = _agent(container, SPEC + ",pool_defer_max=3")
        action = agent.policy(observation)
        self.assertIsNotNone(action)
        self.assertEqual(int(action["item_idx"]), 0)
        self.assertEqual(agent._passed_over, {1: 1})
        self.assertFalse(any(k.startswith("defer_") for k in agent.phase_stats))

    def test_the_soft_box_passed_over_k_times_goes_first(self):
        container, observation = self._observation()
        agent = _agent(container, SPEC + ",pool_defer_max=3")
        agent._passed_over = {1: 3}
        action = agent.policy(observation)
        self.assertIsNotNone(action)
        self.assertEqual(int(action["item_idx"]), 1)
        self.assertEqual(agent.phase_stats.get("defer_calls"), 1)
        self.assertEqual(agent.phase_stats.get("defer_fired"), 1)
        self.assertEqual(agent.phase_stats.get("defer_fired_soft"), 1)
        self.assertIsNone(agent.phase_stats.get("defer_passed"))
        # the hard box was passed over once, the soft box's count stands
        self.assertEqual(agent._passed_over, {0: 1, 1: 3})

    def test_off_the_counts_are_not_kept(self):
        container, observation = self._observation()
        agent = _agent(container)
        agent._passed_over = {1: 9}
        action = agent.policy(observation)
        self.assertEqual(int(action["item_idx"]), 0)
        self.assertEqual(agent._passed_over, {1: 9})


if __name__ == "__main__":
    unittest.main()
