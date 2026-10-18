"""The "seen" modes (reports/wedge/bc-mix.md): the shared seen-class
tracker (``rule_alpha.seen.SeenClasses``), the online rows' table from the
stream (``online_row_depths="seen"``), the pocket guard's frequencies from
the tracker (``pocket_mix="seen"``) and the phase switch's window from the
most frequent seen class (``phase_switch_window="seen"``)."""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.arms import make_arm  # noqa: E402
from bench.scenes import EXTRA_SKUS, SKUS, make_scene  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.pocket import ClassFrequencies  # noqa: E402
from rule_alpha.seen import SAMPLE_ROW_DEPTHS, SAMPLE_WINDOW, SeenClasses  # noqa: E402

SPEC = "ladder-stable@no_cover_other_attribute=true,fast_validate=true"
A, B, C = (0.55, 0.40, 0.24), (0.65, 0.45, 0.25), (0.75, 0.56, 0.27)
H, I = (0.80, 0.60, 0.50), (0.35, 0.25, 0.15)


def _item(index, dims, soft=False, prio=False):
    l, w, h = dims
    return {"index": index, "length": l, "width": w, "height": h, "mass": 5.0 if soft else 9.0,
            "is_soft": soft, "is_prioritized": prio}


def _stream(seed: int, mix: str, n: int) -> list[dict]:
    """A hard-suite stream of one mix (bench.scenes.make_hard_scene's
    weights), hard items only."""
    import random

    rng = random.Random(seed)
    skus = SKUS + EXTRA_SKUS
    weights = {"big": [2, 8, 12, 2, 1, 5, 3, 6, 0, 2], "small": [14, 4, 1, 2, 8, 3, 6, 0, 10, 1],
               "extra": [8, 6, 3, 2, 2, 4, 3, 5, 5, 4], "sample": [s[7] for s in SKUS] + [0, 0, 0]}[mix]
    hard = [(w, sk) for w, sk in zip(weights, skus) if not sk[5]]
    items = []
    for index in range(n):
        sku = rng.choices([sk for _w, sk in hard], weights=[w for w, _sk in hard], k=1)[0]
        items.append(_item(index, sku[1:4]))
    return items


class ConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(DEFAULT_CONFIG.pocket_mix, "fixed")
        self.assertEqual(DEFAULT_CONFIG.online_row_depths, "0.56,0.45,0.4")
        self.assertEqual(DEFAULT_CONFIG.phase_switch_window, "0.40x0.55x0.24")
        self.assertEqual(DEFAULT_CONFIG.seen_classes_min_hard, 6)
        self.assertEqual(DEFAULT_CONFIG.seen_classes_lead, 2)


class SeenClassesTest(unittest.TestCase):
    def test_the_counts_over_a_few_calls(self):
        seen = SeenClasses()
        # call 1: a pool of three, nothing packed
        seen.observe([_item(0, A), _item(1, B), _item(2, (0.45, 0.30, 0.20), soft=True)], [{"packed_items": []}])
        self.assertEqual(seen.total, 3)
        self.assertEqual(seen.hard_total, 2)
        # call 2: item 0 packed, items 1 and 2 still in the pool, item 3 new
        seen.observe([_item(1, B), _item(2, (0.45, 0.30, 0.20), soft=True), _item(3, A)],
                     [{"packed_items": [dict(_item(0, A), pos=(0.3, 0.3, 0.2))]}])
        self.assertEqual(seen.total, 4)
        self.assertEqual(seen.hard_total, 3)
        self.assertEqual(seen.counts[A], 2)
        self.assertEqual(seen.counts[B], 1)
        # call 3: the same observation again counts nothing twice
        seen.observe([_item(1, B), _item(3, A)], [{"packed_items": [dict(_item(0, A), pos=(0.3, 0.3, 0.2))]}])
        self.assertEqual(seen.total, 4)
        self.assertEqual(seen.hard_classes(), [(A, 2), (B, 1)])
        self.assertEqual(seen.most_frequent_hard(), A)
        self.assertEqual(seen.most_frequent_hard(lead=2), None)
        self.assertEqual(seen.smallest_hard(), A)
        # the soft class is not a hard class
        self.assertNotIn((0.45, 0.30, 0.20), dict(seen.hard_classes()))

    def test_the_sample_streams_reproduce_the_fixed_tables(self):
        for task in ("B", "C"):
            scene = make_scene(0, "sample", task)
            seen = SeenClasses()
            for n, item in enumerate(scene.items):
                seen.observe([item], [])
                # the row table is the fixed one at every call, before and
                # after the prior period
                self.assertEqual(seen.row_depth_table(6), list(SAMPLE_ROW_DEPTHS), (task, n))
                # the window is the sample's at every call: the A and B
                # classes run neck and neck and the lead of 2 holds the
                # fallback through their crossings
                self.assertEqual(seen.window(6), SAMPLE_WINDOW, (task, n))
            self.assertEqual(seen.most_frequent_hard(), A)
            self.assertEqual(seen.smallest_hard(), A)
            self.assertEqual(seen.hard_total, 31)

    def test_the_big_and_small_mixes_move_the_tables(self):
        big = SeenClasses()
        for item in _stream(1, "big", 30):
            big.observe([item], [])
        self.assertIn(0.6, big.row_depth_table(6))
        self.assertEqual(big.row_depth_table(6)[0], 0.6)
        self.assertEqual(big.most_frequent_hard(), C)
        self.assertEqual(big.window(6), "0.56x0.75x0.27")
        small = SeenClasses()
        for item in _stream(2, "small", 30):
            small.observe([item], [])
        self.assertIn(0.25, small.row_depth_table(6))
        self.assertEqual(small.row_depth_table(6), [0.56, 0.45, 0.40, 0.25])
        self.assertEqual(small.smallest_hard(), I)
        self.assertEqual(small.window(6, "seen-smallest"), "0.25x0.35x0.15")
        # the prior period: the fixed tables whatever has been seen
        early = SeenClasses()
        for item in _stream(1, "big", 5):
            early.observe([item], [])
        self.assertEqual(early.row_depth_table(6), list(SAMPLE_ROW_DEPTHS))
        self.assertEqual(early.window(6), SAMPLE_WINDOW)

    def test_the_mix_for_a_sampler(self):
        prior = {A: (8.0, False, 13.0), B: (13.0, False, 11.0)}
        seen = SeenClasses()
        for item in _stream(1, "big", 9):
            seen.observe([item], [])
        mix = seen.mix(prior, prior_weight=10.0, min_seen=10)
        self.assertEqual(set(mix), {A, B})  # the prior alone under 10 seen
        self.assertAlmostEqual(sum(v[2] for v in mix.values()), 10.0)
        seen.observe([_item(99, H)], [])
        mix = seen.mix(prior, prior_weight=10.0, min_seen=10)
        self.assertIn(H, mix)
        self.assertAlmostEqual(sum(v[2] for v in mix.values()), 20.0)


class PocketMixTest(unittest.TestCase):
    def test_fixed_counts_from_the_first_item_and_seen_waits_for_ten(self):
        fixed = ClassFrequencies(prior_count=4.0)
        prior = dict(fixed.counts)
        fixed.observe([_item(0, H)])
        self.assertEqual(fixed.counts[fixed._key(*H)], 1.0)
        for key, value in prior.items():
            self.assertAlmostEqual(fixed.counts[key], value)
        seen = SeenClasses()
        seen.observe([_item(0, H)], [])
        adaptive = ClassFrequencies(prior_count=4.0)
        adaptive.observe([_item(0, H)])
        adaptive.set_seen(seen, prior_weight=10.0, min_seen=10)
        self.assertNotIn(adaptive._key(*H), adaptive.counts)
        self.assertAlmostEqual(sum(adaptive.counts.values()), 10.0)
        for item in _stream(3, "big", 12):
            seen.observe([item], [])
        adaptive.set_seen(seen, prior_weight=10.0, min_seen=10)
        self.assertIn(adaptive._key(*H), adaptive.counts)
        self.assertAlmostEqual(sum(adaptive.counts.values()), 10.0 + seen.hard_total)
        # the big class is now expected
        probs = dict(((l, w, h), p) for l, w, h, p in adaptive.arrival_probabilities())
        self.assertGreater(probs[adaptive._key(*H)], 0.5)

    def test_the_agent_feeds_the_tracker_to_the_guard(self):
        container = make_scene(1, "c1", "C").rule_alpha_containers()[0]
        agent = make_arm(SPEC + ",pocket_guard=true,pocket_mix=seen")(None)
        agent.get_init_states({"container_list": [container]})
        pool = [_item(i, H) for i in range(12)]
        agent.policy({"container_list": [container], "pool_list": pool})
        self.assertEqual(agent.seen_classes.hard_total, 12)
        freq = agent.pocket.frequencies
        self.assertAlmostEqual(freq.counts[freq._key(*H)], 12.0)
        self.assertAlmostEqual(sum(freq.counts.values()), 22.0)


class PhaseWindowTest(unittest.TestCase):
    def _agent(self, extra=""):
        container = make_scene(1, "c1", "C").rule_alpha_containers()[0]
        agent = make_arm(SPEC + extra)(None)
        agent.get_init_states({"container_list": [container]})
        return agent, container

    def test_fixed_and_seen(self):
        agent, container = self._agent(",phase_switch=true")
        self.assertEqual(agent._phase_window(), "0.40x0.55x0.24")
        self.assertEqual(agent._seen_modes(), frozenset())
        agent, container = self._agent(",phase_switch=true,phase_switch_window=seen")
        self.assertEqual(agent._seen_modes(), frozenset({"window"}))
        # the prior period: the sample's window
        agent.policy({"container_list": [container], "pool_list": [_item(i, C) for i in range(3)]})
        self.assertEqual(agent._phase_window(), SAMPLE_WINDOW)
        # after it, the most frequent seen class
        agent.policy({"container_list": [container], "pool_list": [_item(i, C) for i in range(8)]})
        self.assertEqual(agent._phase_window(), "0.56x0.75x0.27")
        self.assertEqual(agent.phase_stats.get("seen_window"), "0.56x0.75x0.27")
        agent, container = self._agent(",phase_switch=true,phase_switch_window=seen-smallest")
        agent.policy({"container_list": [container], "pool_list": [_item(i, C) for i in range(7)] + [_item(9, I)]})
        self.assertEqual(agent._phase_window(), "0.25x0.35x0.15")

    def test_the_sample_stream_keeps_the_sample_window(self):
        scene = make_scene(0, "sample", "B")
        agent, container = self._agent(",phase_switch=true,phase_switch_window=seen")
        agent.seen_classes.observe([dict(i) for i in scene.items], [])
        self.assertEqual(agent._phase_window(), SAMPLE_WINDOW)
        self.assertIsNone(agent.phase_stats.get("seen_window"))


class SeenRowsTest(unittest.TestCase):
    """``online_row_depths="seen"``: the table from the stream, the rows
    that hold a box kept where they were."""

    ROWS = ",online_planner=rows,online_row_depths=seen,seen_classes_min_hard=2"

    def _agent(self, extra=""):
        container = make_scene(1, "c1", "C").rule_alpha_containers()[0]
        agent = make_arm(SPEC + self.ROWS + extra)(None)
        agent.get_init_states({"container_list": [container]})
        return agent, container

    def test_the_sample_classes_give_the_fixed_lines(self):
        from rule_alpha.planner import online_row_lines

        agent, container = self._agent()
        pool = [_item(0, A), _item(1, B), _item(2, C)]
        action = agent.policy({"container_list": [container], "pool_list": pool})
        self.assertIsNotNone(action)
        self.assertEqual(agent.last_decision.placement.archetype, "online-rows")
        fixed = online_row_lines(agent.board.model(0), agent.config, [0.56, 0.45, 0.40])
        self.assertEqual(agent._seen_rows[0], fixed)
        self.assertEqual(len(fixed), 2)  # 0.56 and 0.45 fit the ULD's floor, 0.40 does not

    def test_a_new_class_lays_a_row_in_front_and_the_occupied_row_stays(self):
        agent, container = self._agent()
        board = layer1.Board([container], agent.config)
        # the first box: the sample's table, the box in the back row
        pool = [_item(0, A), _item(1, A)]
        action = agent.policy({"container_list": board.containers, "pool_list": pool})
        self.assertIsNotNone(action)
        board.apply(agent.last_decision.placement)
        first = agent._seen_rows[0]
        back = first[0]
        placed = board.container(0)["packed_items"][0]
        self.assertTrue(back[0] - back[1] <= placed["pos"][1] <= back[0])
        # the stream shows the big class: the table gains a 0.60 row, the
        # occupied 0.56 row stays, the empty 0.45 row in front of it is
        # laid again as the 0.60 row
        pool = [_item(1, A)] + [_item(i, H) for i in range(2, 6)]
        action = agent.policy({"container_list": board.containers, "pool_list": pool})
        self.assertIsNotNone(action)
        lines = agent._seen_rows[0]
        self.assertEqual(lines[0], back)
        self.assertAlmostEqual(lines[1][1], 0.60)
        self.assertEqual(agent.seen_classes.row_depth_table(2), [0.6, 0.56, 0.45, 0.4])
        self.assertEqual(len(lines), 2)
        # and again, unchanged: the lines are stable while the table is
        again = agent._seen_row_lines(0)
        self.assertEqual(again, lines)

    def test_a_container_no_box_has_reached_follows_the_table(self):
        agent, container = self._agent()
        agent.policy({"container_list": [container], "pool_list": [_item(i, H) for i in range(4)]})
        lines = agent._seen_rows[0]
        self.assertAlmostEqual(lines[0][1], 0.60)
        self.assertAlmostEqual(lines[1][1], 0.56)


if __name__ == "__main__":
    unittest.main()
