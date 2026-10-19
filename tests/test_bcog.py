"""Task B's centre-of-mass levers (reports/wedge/b-cog.md): the ladder's
tie-break by the resulting load's centre height (``config.ladder_com_weight``)
and the pool order toward the heavy hard boxes (``config.pool_com_order``).
Both are off by default."""

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
from rule_alpha.layer1 import AABB, Candidate  # noqa: E402

HARD = {"index": 5, "length": 0.4, "width": 0.3, "height": 0.25, "mass": 6.0,
        "is_soft": False, "is_prioritized": False}


def _board(config, packed=()):
    containers = make_scene(1, "c1", "C").rule_alpha_containers()
    thickness = float(containers[0]["thickness"])
    for n, (z_above, mass) in enumerate(packed):
        containers[0]["packed_items"].append(
            {"index": 100 + n, "length": 0.3, "width": 0.3, "height": 0.2, "mass": mass,
             "is_soft": False, "is_prioritized": False,
             "pos": (0.5, 0.5, thickness + z_above), "orn": (0.0, 0.0, 0.0, 1.0)})
    return layer1.Board(containers, config), thickness


def _candidate(config, z_centre, y_back=0.4, mass=6.0):
    profile = cls.classify_item(5, dict(HARD, mass=mass), config)
    orientation = profile.orientations[0]
    box = AABB((0.2, 0.2, z_centre), (0.4, 0.3, 0.25))
    return Candidate(box=box, profile=profile, orientation=orientation, container_idx=0,
                     surface="floor", surface_name="floor", role="none",
                     features={"footprint": 0.12, "y_back": y_back, "frontier_contact": 0.0, "top_z": 0.0})


class ConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(DEFAULT_CONFIG.ladder_com_weight, 0.0)
        self.assertFalse(DEFAULT_CONFIG.pool_com_order)
        self.assertTrue(DEFAULT_CONFIG.ladder_com_secured)
        self.assertTrue(DEFAULT_CONFIG.pool_com_secured)


class LadderComTest(unittest.TestCase):
    def setUp(self):
        self.config = dataclasses.replace(DEFAULT_CONFIG, ladder_com_weight=1.0)
        self.board, self.thickness = _board(self.config, packed=[(0.3, 5.0)])
        self.high = _candidate(self.config, self.thickness + 0.9)
        self.low = _candidate(self.config, self.thickness + 0.125)

    def test_load_ratio_after_is_the_mass_weighted_height(self):
        height = float(self.board.models[0].height)
        z_floor = float(self.board.models[0].z_floor)
        expect = (5.0 * (self.thickness + 0.3 - z_floor) + 6.0 * (self.thickness + 0.125 - z_floor)) / 11.0 / height
        self.assertAlmostEqual(layer1.load_ratio_after(self.low, self.board), expect, places=9)
        self.assertLess(layer1.load_ratio_after(self.low, self.board),
                        layer1.load_ratio_after(self.high, self.board))

    def test_ties_on_the_leading_term_go_to_the_lower_pose(self):
        # equal leading terms, the high pose first in the rung's own order
        self.high.features["frontier_contact"] = 1.0
        self.high.features["top_z"] = 0.1
        self.low.features["top_z"] = 0.5
        off = layer1.rung_order(layer1.A_MAX_FOOTPRINT, [self.low, self.high], DEFAULT_CONFIG, self.board)
        on = layer1.rung_order(layer1.A_MAX_FOOTPRINT, [self.low, self.high], self.config, self.board)
        self.assertIs(off[0], self.high)
        self.assertEqual({id(c) for c in on}, {id(self.high), id(self.low)})
        self.assertIs(on[0], self.low)

    def test_a_better_leading_term_keeps_priority(self):
        deeper = _candidate(self.config, self.thickness + 0.9, y_back=0.9)
        deeper.features["footprint"] = 0.30
        on = layer1.rung_order(layer1.A_MAX_FOOTPRINT, [self.low, deeper], self.config, self.board)
        self.assertIs(on[0], deeper)           # the larger footprint is outside the band

    def test_no_board_or_inactive_board_leaves_the_order(self):
        self.high.features["frontier_contact"] = 1.0
        base = layer1.rung_order(layer1.A_MAX_FOOTPRINT, [self.high, self.low], DEFAULT_CONFIG)
        self.assertEqual(layer1.rung_order(layer1.A_MAX_FOOTPRINT, [self.high, self.low], self.config), base)
        self.board.ladder_com_active = False
        self.assertEqual(layer1.rung_order(layer1.A_MAX_FOOTPRINT, [self.high, self.low], self.config, self.board), base)


class PoolOrderTest(unittest.TestCase):
    def _agent(self, spec):
        scene = make_scene(1, "c1", "B")
        agent = make_arm(spec)(scene)
        agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        agent.board = layer1.Board(scene.rule_alpha_containers(), agent.config)
        agent._deferred_now = set()
        return agent

    def _pairs(self, agent, masses):
        out = []
        for n, mass in enumerate(masses):
            item = dict(HARD, index=n, mass=mass, length=0.4 + 0.01 * n)
            out.append((n, cls.classify_item(n, item, agent.config)))
        return out

    def test_heavy_first_only_when_secured(self):
        agent = self._agent("ladder-stable@pool_com_order=true,count_mode=true")
        pairs = self._pairs(agent, [3.0, 9.0, 5.0])
        agent._manifest_total = 40
        agent._placed_now = 0
        self.assertEqual(agent._com_order(list(pairs)), pairs)       # under the threshold: untouched
        agent._placed_now = 40
        out = agent._com_order(list(pairs))
        self.assertEqual([p.mass for _i, p in out], [9.0, 5.0, 3.0])
        self.assertEqual(agent._com_first, 0)
        self.assertEqual(agent._com_promoted, {1, 2})

    def test_hold_skips_a_high_pose_of_a_promoted_item_only(self):
        agent = self._agent("ladder-stable@pool_com_order=true,count_mode=true")
        profile = self._pairs(agent, [3.0, 9.0])[1][1]
        floor = float(agent.board.models[0].z_floor)

        class P:
            container_idx = 0

            def __init__(self, z):
                self.box = AABB((0.2, 0.2, z + 0.125), (0.4, 0.3, 0.25))

        agent._com_promoted = {1}
        self.assertFalse(agent._com_hold(profile, P(floor)))
        self.assertTrue(agent._com_hold(profile, P(floor + 0.6)))
        agent._com_promoted = set()
        self.assertFalse(agent._com_hold(profile, P(floor + 0.6)))


if __name__ == "__main__":
    unittest.main()
